import json
import hashlib
import asyncio
import sentry_sdk
import pybreaker
from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse

from app.bus import publish as event_bus_publish
from app.agent.schemas import EmergencyInput, SupplierRoute, RouteResult
from app.agent.services import parse_emergency
from app.inventory.models import find_supplier, decrement_inventory, increment_inventory
from app.routing.engine import compute_shortest_paths, reconstruct_path
from app.routing.circuit import breaker, get_fallback_result, toggle_breaker, reset_breaker
from app.database import supabase

CACHE_TTL_SECONDS = 300
MAX_REQUEST_QUANTITY = 50
SECONDS_PER_DISTANCE_UNIT = 1.0   # tune this to control demo speed
MIN_DELIVERY_SECONDS = 3
MAX_DELIVERY_SECONDS = 12

router = APIRouter()


async def _simulate_fallback_delivery(
    destination: str, supplier: str, item: str, quantity: int
) -> None:
    await event_bus_publish({
        "type": "in_transit",
        "supplier": supplier,
        "destination": destination,
        "item": item,
        "quantity": quantity,
        "eta_seconds": MIN_DELIVERY_SECONDS,
    })
    await asyncio.sleep(MIN_DELIVERY_SECONDS)
    await decrement_inventory(supabase, supplier, item, quantity)
    await increment_inventory(supabase, destination, item, quantity)
    await event_bus_publish({
        "type": "delivery_complete",
        "destination": destination,
        "item": item,
        "quantity": quantity,
    })
    rows = await _fetch_inventory_rows()
    await event_bus_publish({"type": "inventory_updated", "rows": rows})


async def _simulate_delivery(
    destination: str,
    routes: list[SupplierRoute],
    item: str,
    total_quantity: int,
) -> None:
    max_distance = max((r.distance for r in routes), default=0.0)
    eta = max(MIN_DELIVERY_SECONDS, min(MAX_DELIVERY_SECONDS, round(max_distance * SECONDS_PER_DISTANCE_UNIT)))
    for route in routes:
        await event_bus_publish({
            "type": "in_transit",
            "supplier": route.supplier_id,
            "destination": destination,
            "item": item,
            "quantity": route.quantity_allocated,
            "eta_seconds": eta,
        })
    await asyncio.sleep(eta)
    await increment_inventory(supabase, destination, item, total_quantity)
    await event_bus_publish({
        "type": "delivery_complete",
        "destination": destination,
        "item": item,
        "quantity": total_quantity,
    })
    rows = await _fetch_inventory_rows()
    await event_bus_publish({"type": "inventory_updated", "rows": rows})


async def _fetch_inventory_rows() -> list[dict[str, str | int | float]]:
    response = await asyncio.to_thread(
        lambda: supabase.table("hospital_inventory")
        .select("name, item, quantity, x, y")
        .order("name")
        .order("item")
        .execute()
    )
    return response.data or []


@router.post("/emergency")
async def route_emergency(
    request: Request,
    body: EmergencyInput | None = None,
    message: str | None = Form(default=None),
    selected_hospital: str | None = Form(default=None),
) -> dict:
    redis = request.app.state.redis
    graph = request.app.state.static_network_graph
    hospital_node_map = request.app.state.hospital_node_map

    emergency_input = body
    if emergency_input is None and message:
        emergency_input = EmergencyInput(message=message)
    if emergency_input is None:
        raise HTTPException(422, "Emergency message is required.")

    known_items = list(request.app.state.known_items) if hasattr(request.app.state, "known_items") else None
    try:
        emergency = await parse_emergency(
            emergency_input.message,
            list(hospital_node_map.keys()),
            known_items,
            fixed_hospital=selected_hospital or None,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    # Normalize item name: case-insensitive match against known inventory items
    if known_items:
        lower_map = {i.lower(): i for i in known_items}
        emergency.item = lower_map.get(emergency.item.lower(), emergency.item)

    if selected_hospital and emergency.hospital.lower() != selected_hospital.lower():
        raise HTTPException(
            403,
            f"Access denied: you are logged in as {selected_hospital!r} but this request "
            f"is for {emergency.hospital!r}. Switch to Full Command or re-submit from the correct terminal.",
        )

    if emergency.quantity > MAX_REQUEST_QUANTITY:
        raise HTTPException(
            422,
            f"Request exceeds single-dispatch limit: {emergency.quantity} units requested, "
            f"max {MAX_REQUEST_QUANTITY}. Split into multiple alerts or contact regional command.",
        )

    destination_node = hospital_node_map.get(emergency.hospital)
    if not destination_node:
        raise HTTPException(422, f"Hospital '{emergency.hospital}' not in network.")

    # Circuit check BEFORE cache — open circuit must short-circuit everything
    if breaker.current_state == "open":
        fallback = get_fallback_result(destination_node)
        fallback["routes"][0]["quantity_allocated"] = emergency.quantity
        fallback["total_quantity"] = emergency.quantity
        await event_bus_publish({"type": "circuit_open"})
        await event_bus_publish({"type": "route_dispatched", "result": fallback})
        supplier = fallback["routes"][0]["supplier_id"]
        asyncio.create_task(_simulate_fallback_delivery(
            destination_node, supplier, emergency.item, emergency.quantity
        ))
        return fallback

    cache_key = hashlib.sha256(
        (emergency.hospital + emergency.item + emergency.urgency).encode()
    ).hexdigest()

    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        success = await decrement_inventory(
            supabase, data["supplier_id"], emergency.item, emergency.quantity
        )
        if success:
            route = SupplierRoute(
                supplier_id=data["supplier_id"],
                quantity_allocated=emergency.quantity,
                path=data["path"],
                distance=data["distance"],
            )
            result = RouteResult(
                routes=[route], total_quantity=emergency.quantity, partial=False
            )
            await event_bus_publish({"type": "route_dispatched", "result": result.model_dump()})
            inventory_rows = await _fetch_inventory_rows()
            await event_bus_publish({"type": "inventory_updated", "rows": inventory_rows})
            asyncio.create_task(
                _simulate_delivery(emergency.hospital, [route], emergency.item, emergency.quantity)
            )
            return result.model_dump()
        # Stale entry — supplier exhausted since caching; evict and recompute
        await redis.delete(cache_key)

    try:
        distances, predecessors = breaker.call(
            compute_shortest_paths, destination_node, graph
        )
    except pybreaker.CircuitBreakerError:
        sentry_sdk.capture_message(
            "StatRoute circuit open — routing fallback activated", level="warning"
        )
        fallback = get_fallback_result(destination_node)
        fallback["routes"][0]["quantity_allocated"] = emergency.quantity
        fallback["total_quantity"] = emergency.quantity
        await event_bus_publish({"type": "circuit_open"})
        await event_bus_publish({"type": "route_dispatched", "result": fallback})
        supplier = fallback["routes"][0]["supplier_id"]
        asyncio.create_task(_simulate_fallback_delivery(
            destination_node, supplier, emergency.item, emergency.quantity
        ))
        return fallback

    suppliers = await find_supplier(supabase, emergency.item)
    ranked = sorted(
        [s for s in suppliers if s.id != emergency.hospital and s.node in distances],
        key=lambda s: distances[s.node],
    )
    if not ranked:
        raise HTTPException(404, f"No regional inventory available for: {emergency.item}")

    routes: list[SupplierRoute] = []
    remaining = emergency.quantity
    for supplier in ranked:
        if remaining <= 0:
            break
        allocated = min(supplier.available_qty, remaining)
        path = reconstruct_path(predecessors, destination_node, supplier.node)
        routes.append(
            SupplierRoute(
                supplier_id=supplier.id,
                quantity_allocated=allocated,
                path=path,
                distance=distances[supplier.node],
            )
        )
        remaining -= allocated

    if remaining > 0:
        raise HTTPException(
            409, f"Insufficient regional inventory. Short by {remaining} units."
        )

    decremented: list[tuple[str, int]] = []
    for route in routes:
        success = await decrement_inventory(
            supabase, route.supplier_id, emergency.item, route.quantity_allocated
        )
        if not success:
            for sup_id, qty in decremented:
                await increment_inventory(supabase, sup_id, emergency.item, qty)
            raise HTTPException(409, f"Concurrent depletion at {route.supplier_id}.")
        decremented.append((route.supplier_id, route.quantity_allocated))

    result = RouteResult(
        routes=routes,
        total_quantity=emergency.quantity,
        partial=len(routes) > 1,
    )

    # Only cache single-supplier results; partial routes span multiple inventory states
    if not result.partial:
        await redis.set(
            cache_key,
            json.dumps({
                "supplier_id": routes[0].supplier_id,
                "path": routes[0].path,
                "distance": routes[0].distance,
            }),
            ex=CACHE_TTL_SECONDS,
        )

    await event_bus_publish({"type": "route_dispatched", "result": result.model_dump()})
    inventory_rows = await _fetch_inventory_rows()
    await event_bus_publish({"type": "inventory_updated", "rows": inventory_rows})
    asyncio.create_task(
        _simulate_delivery(emergency.hospital, routes, emergency.item, emergency.quantity)
    )
    return result.model_dump()


@router.post("/chaos/toggle")
async def chaos_toggle() -> HTMLResponse:
    toggle_breaker()
    await event_bus_publish({"type": "circuit_open", "source": "chaos_toggle"})
    return HTMLResponse(
        '<span id="circuit-breaker-badge" class="rounded-full border border-rose-500/70 bg-rose-500/10 px-3 py-1 font-medium text-rose-300">OPEN</span>'
    )


@router.post("/chaos/reset")
async def chaos_reset() -> HTMLResponse:
    reset_breaker()
    await event_bus_publish({"type": "circuit_closed"})
    return HTMLResponse(
        '<span id="circuit-breaker-badge" class="rounded-full border border-emerald-500/60 bg-emerald-500/10 px-3 py-1 font-medium text-emerald-300">CLOSED</span>'
    )
