import asyncio

from fastapi import APIRouter, Request

from app.bus import event_bus
from app.database import supabase
from app.inventory.models import load_initial_map_graph

router = APIRouter()

SEED_INVENTORY_ROWS: list[dict[str, str | int | float]] = [
    {
        "name": "St. Jude",
        "item": "O-negative blood",
        "quantity": 0,
        "x": 0.0,
        "y": 0.0,
    },
    {
        "name": "City General",
        "item": "O-negative blood",
        "quantity": 50,
        "x": 3.0,
        "y": 4.0,
    },
    {
        "name": "Metro Health",
        "item": "O-negative blood",
        "quantity": 30,
        "x": 7.0,
        "y": 1.0,
    },
    {
        "name": "Riverside Medical",
        "item": "O-negative blood",
        "quantity": 20,
        "x": 2.0,
        "y": 8.0,
    },
    {
        "name": "Downtown ER",
        "item": "O-negative blood",
        "quantity": 45,
        "x": 5.0,
        "y": 5.0,
    },
    {
        "name": "St. Jude",
        "item": "epinephrine",
        "quantity": 10,
        "x": 0.0,
        "y": 0.0,
    },
    {
        "name": "City General",
        "item": "epinephrine",
        "quantity": 0,
        "x": 3.0,
        "y": 4.0,
    },
    {
        "name": "Metro Health",
        "item": "epinephrine",
        "quantity": 25,
        "x": 7.0,
        "y": 1.0,
    },
    {
        "name": "Riverside Medical",
        "item": "epinephrine",
        "quantity": 15,
        "x": 2.0,
        "y": 8.0,
    },
    {
        "name": "Downtown ER",
        "item": "epinephrine",
        "quantity": 30,
        "x": 5.0,
        "y": 5.0,
    },
]


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
    await event_bus.put(
        {
            "type": "inventory_snapshot",
            "rows": len(rows),
        }
    )
    return rows


@router.post("/seed")
async def seed_inventory(request: Request) -> dict[str, str | int]:
    await asyncio.to_thread(
        lambda: supabase.table("hospital_inventory").delete().neq("name", "").execute()
    )
    await asyncio.to_thread(
        lambda: supabase.table("hospital_inventory").insert(SEED_INVENTORY_ROWS).execute()
    )

    graph, hospital_node_map = await load_initial_map_graph(supabase)
    request.app.state.static_network_graph = graph
    request.app.state.hospital_node_map = hospital_node_map
    await request.app.state.redis.flushdb()

    rows = await _fetch_inventory_rows()
    await event_bus.put({"type": "inventory_updated", "rows": rows})
    return {"status": "seeded", "rows": len(SEED_INVENTORY_ROWS)}
