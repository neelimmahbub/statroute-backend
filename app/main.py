import json
import html
import sentry_sdk
import redis.asyncio as aioredis
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.bus import event_bus
from app.database import supabase
from app.inventory.models import load_initial_map_graph
from app.routing.router import router as routing_router
from app.inventory.router import router as inventory_router
from app.dashboard.views import router as dashboard_router

settings = get_settings()

sentry_sdk.init(
    dsn=settings.sentry_dsn,
    traces_sample_rate=0.1,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    graph, hospital_node_map = await load_initial_map_graph(supabase)
    app.state.static_network_graph = graph
    app.state.hospital_node_map = hospital_node_map
    yield
    await app.state.redis.aclose()


app = FastAPI(lifespan=lifespan, title="StatRoute")

app.include_router(routing_router, prefix="/api")
app.include_router(inventory_router, prefix="/api/inventory")
app.include_router(dashboard_router)


def _render_route_card(event: dict) -> str:
    result = event.get("result", {})
    routes = result.get("routes", [])
    if not routes:
        return (
            '<article class="rounded-lg border border-slate-700 bg-slate-950 p-3 text-sm">'
            '<p class="text-slate-300">Route dispatched, but no route rows were returned.</p>'
            "</article>"
        )

    route_parts: list[str] = []
    for route in routes:
        supplier = html.escape(str(route.get("supplier_id", "UNKNOWN")))
        qty = int(route.get("quantity_allocated", 0))
        distance = float(route.get("distance", 0.0))
        path_nodes = [html.escape(str(node)) for node in route.get("path", [])]
        path_text = " -> ".join(path_nodes) if path_nodes else "n/a"
        route_parts.append(
            f'<li class="rounded-md bg-slate-900 p-2">'
            f'<p class="font-medium text-slate-100">{supplier}</p>'
            f'<p class="text-xs text-slate-300">Qty: {qty} | Distance: {distance:.2f}</p>'
            f'<p class="text-xs text-slate-400">{path_text}</p>'
            f"</li>"
        )

    total_quantity = int(result.get("total_quantity", 0))
    partial = bool(result.get("partial", False))
    title = "Partial fulfillment" if partial else "Dispatched"
    return (
        '<article class="rounded-lg border border-indigo-700/60 bg-indigo-950/40 p-3 text-sm">'
        f'<div class="mb-2 flex items-center justify-between"><p class="font-semibold text-indigo-200">{title}</p>'
        f'<p class="text-xs text-indigo-300">Total qty: {total_quantity}</p></div>'
        f'<ul class="space-y-2">{"".join(route_parts)}</ul>'
        "</article>"
    )


def _render_inventory_rows(event: dict) -> str:
    rows = event.get("rows", [])
    if not rows:
        return '<tr><td class="px-3 py-3 text-slate-400" colspan="4">No inventory records found.</td></tr>'

    rendered_rows: list[str] = []
    for row in rows:
        name = html.escape(str(row.get("name", "")))
        item = html.escape(str(row.get("item", "")))
        quantity = int(row.get("quantity", 0))
        x_coord = float(row.get("x", 0.0))
        y_coord = float(row.get("y", 0.0))
        qty_style = "text-rose-300" if quantity <= 0 else "text-emerald-300"
        rendered_rows.append(
            "<tr>"
            f'<td class="px-3 py-2 text-slate-100">{name}</td>'
            f'<td class="px-3 py-2 text-slate-300">{item}</td>'
            f'<td class="px-3 py-2 font-semibold {qty_style}">{quantity}</td>'
            f'<td class="px-3 py-2 text-slate-400">({x_coord:.1f}, {y_coord:.1f})</td>'
            "</tr>"
        )
    return "".join(rendered_rows)


def _render_circuit_badge(event_type: str) -> str:
    if event_type == "circuit_open":
        return (
            '<span id="circuit-breaker-badge" class="rounded-full border border-rose-500/70 bg-rose-500/10 px-3 py-1 font-medium text-rose-300">OPEN</span>'
        )
    return (
        '<span id="circuit-breaker-badge" class="rounded-full border border-emerald-500/60 bg-emerald-500/10 px-3 py-1 font-medium text-emerald-300">CLOSED</span>'
    )


def _build_sse_payload(event: dict) -> str:
    event_type = str(event.get("type", "message"))
    if event_type == "route_dispatched":
        return _render_route_card(event)
    if event_type == "inventory_updated":
        return _render_inventory_rows(event)
    if event_type in {"circuit_open", "circuit_closed"}:
        return _render_circuit_badge(event_type)
    return html.escape(json.dumps(event))


@app.get("/events")
async def sse_events():
    async def generator():
        while True:
            event = await event_bus.get()
            event_type = str(event.get("type", "message"))
            payload = _build_sse_payload(event)
            yield f"event: {event_type}\ndata: {payload}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
