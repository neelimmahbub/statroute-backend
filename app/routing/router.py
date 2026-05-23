import json
import hashlib
import asyncio
import sentry_sdk
import pybreaker
from fastapi import APIRouter, Form, Request, HTTPException
from fastapi.responses import HTMLResponse

from app.bus import event_bus
from app.agent.schemas import EmergencyInput, SupplierRoute, RouteResult
from app.agent.services import parse_emergency
from app.inventory.models import find_supplier, decrement_inventory, increment_inventory
from app.routing.engine import compute_shortest_paths, reconstruct_path
from app.routing.circuit import breaker, STATIC_FALLBACK_PATH, toggle_breaker, reset_breaker
from app.database import supabase

CACHE_TTL_SECONDS = 300
DELIVERY_SIM_SECONDS = 5
MAX_REQUEST_QUANTITY = 50

router = APIRouter()


async def _simulate_delivery(
    destination: str,
    routes: list[SupplierRoute],
    item: str,
    total_quantity: int,
) -> None:
    for route in routes:
        await event_bus.put({
            "type": "in_transit",
            "supplier": route.supplier_id,
            "destination": destination,
            "item": item,
            "quantity": route.quantity_allocated,
            "eta_seconds": DELIVERY_SIM_SECONDS,
        })
    await asyncio.sleep(DELIVERY_SIM_SECONDS)
    await increment_inventory(supabase, destination, item, total_quantity)
    await event_bus.put({
        "type": "delivery_complete",
        "destination": destination,
        "item": item,
        "quantity": total_quantity,
    })
    rows = await _fetch_inventory_rows()
    await event_bus.put({"type": "inventory_updated", "rows": rows})


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

    emergency = await parse_emergency(
        emergency_input.message, list(hospital_node_map.keys())
    )

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
            await event_bus.put({"type": "route_dispatched", "result": result.model_dump()})
            inventory_rows = await _fetch_inventory_rows()
            await event_bus.put({"type": "inventory_updated", "rows": inventory_rows})
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
        await event_bus.put({"type": "circuit_open"})
        return STATIC_FALLBACK_PATH

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

    for route in routes:
        success = await decrement_inventory(
            supabase, route.supplier_id, emergency.item, route.quantity_allocated
        )
        if not success:
            raise HTTPException(409, f"Concurrent depletion at {route.supplier_id}.")

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

    await event_bus.put({"type": "route_dispatched", "result": result.model_dump()})
    inventory_rows = await _fetch_inventory_rows()
    await event_bus.put({"type": "inventory_updated", "rows": inventory_rows})
    asyncio.create_task(
        _simulate_delivery(emergency.hospital, routes, emergency.item, emergency.quantity)
    )
    return result.model_dump()


@router.post("/chaos/toggle")
async def chaos_toggle() -> HTMLResponse:
    toggle_breaker()
    await event_bus.put({"type": "circuit_open", "source": "chaos_toggle"})
    return HTMLResponse(
        '<span id="circuit-breaker-badge" class="rounded-full border border-rose-500/70 bg-rose-500/10 px-3 py-1 font-medium text-rose-300">OPEN</span>'
    )


@router.post("/chaos/reset")
async def chaos_reset() -> HTMLResponse:
    reset_breaker()
    await event_bus.put({"type": "circuit_closed"})
    return HTMLResponse(
        '<span id="circuit-breaker-badge" class="rounded-full border border-emerald-500/60 bg-emerald-500/10 px-3 py-1 font-medium text-emerald-300">CLOSED</span>'
    )
