import asyncio

from fastapi import APIRouter, Request

from app.bus import publish as event_bus_publish
from app.database import supabase
from app.inventory.models import load_initial_map_graph, reset_seed_data

router = APIRouter()


async def _fetch_inventory_rows() -> list[dict[str, str | int | float]]:
    response = await asyncio.to_thread(
        lambda: supabase.table("hospital_inventory")
        .select("name, item, quantity, x, y")
        .order("name")
        .order("item")
        .execute()
    )
    return response.data or []


@router.get("")
async def list_inventory() -> list[dict[str, str | int | float]]:
    rows = await _fetch_inventory_rows()
    await event_bus_publish(
        {
            "type": "inventory_snapshot",
            "rows": len(rows),
        }
    )
    return rows


@router.post("/seed/reset")
async def seed_inventory(request: Request) -> dict[str, str | int]:
    """DESTRUCTIVE — wipes and re-seeds inventory, flushes Redis, reloads graph."""
    count = await reset_seed_data(supabase)
    graph, hospital_node_map = await load_initial_map_graph(supabase)
    request.app.state.static_network_graph = graph
    request.app.state.hospital_node_map = hospital_node_map
    await request.app.state.redis.flushdb()
    rows = await _fetch_inventory_rows()
    await event_bus_publish({"type": "inventory_updated", "rows": rows})
    return {"status": "seeded", "rows": count}
