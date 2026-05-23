import asyncio
import math

from supabase import Client

from app.agent.schemas import SupplierNode

SEED_ROWS: list[dict[str, str | int | float]] = [
    {"name": "St. Jude",          "item": "O-negative blood", "quantity": 0,  "x": 0.0, "y": 0.0},
    {"name": "City General",       "item": "O-negative blood", "quantity": 50, "x": 3.0, "y": 4.0},
    {"name": "Metro Health",       "item": "O-negative blood", "quantity": 30, "x": 7.0, "y": 1.0},
    {"name": "Riverside Medical",  "item": "O-negative blood", "quantity": 20, "x": 2.0, "y": 8.0},
    {"name": "Downtown ER",        "item": "O-negative blood", "quantity": 45, "x": 5.0, "y": 5.0},
    {"name": "St. Jude",          "item": "epinephrine",       "quantity": 10, "x": 0.0, "y": 0.0},
    {"name": "City General",       "item": "epinephrine",       "quantity": 0,  "x": 3.0, "y": 4.0},
    {"name": "Metro Health",       "item": "epinephrine",       "quantity": 25, "x": 7.0, "y": 1.0},
    {"name": "Riverside Medical",  "item": "epinephrine",       "quantity": 15, "x": 2.0, "y": 8.0},
    {"name": "Downtown ER",        "item": "epinephrine",       "quantity": 30, "x": 5.0, "y": 5.0},
]


async def reset_seed_data(supabase: Client) -> int:
    """DESTRUCTIVE — wipes hospital_inventory and re-inserts seed rows."""
    await asyncio.to_thread(
        lambda: supabase.table("hospital_inventory").delete().neq("name", "").execute()
    )
    await asyncio.to_thread(
        lambda: supabase.table("hospital_inventory").insert(SEED_ROWS).execute()
    )
    return len(SEED_ROWS)


async def find_supplier(supabase: Client, item: str) -> list[SupplierNode]:
    """
    Args: Supabase client, inventory item name.
    Returns: Hospitals with positive stock for the requested item.
    """
    response = await asyncio.to_thread(
        lambda: supabase.table("hospital_inventory")
        .select("name, quantity, x, y")
        .eq("item", item)
        .gt("quantity", 0)
        .execute()
    )
    rows = response.data or []
    return [
        SupplierNode(
            id=row["name"],
            node=row["name"],
            available_qty=row["quantity"],
            x=row["x"],
            y=row["y"],
        )
        for row in rows
    ]


async def increment_inventory(
    supabase: Client,
    hospital: str,
    item: str,
    qty: int,
) -> bool:
    """Increment destination inventory after simulated delivery arrival."""
    res = await asyncio.to_thread(
        lambda: supabase.table("hospital_inventory")
        .select("quantity")
        .eq("name", hospital)
        .eq("item", item)
        .execute()
    )
    if not res.data:
        return False
    new_qty = res.data[0]["quantity"] + qty
    res2 = await asyncio.to_thread(
        lambda: supabase.table("hospital_inventory")
        .update({"quantity": new_qty})
        .eq("name", hospital)
        .eq("item", item)
        .execute()
    )
    return bool(res2.data)


async def decrement_inventory(
    supabase: Client,
    supplier_id: str,
    item: str,
    qty: int,
) -> bool:
    """
    Args: Supabase client, supplier hospital name, inventory item, decrement quantity.
    Returns: True when at least one row was updated, otherwise False.
    """
    response = await asyncio.to_thread(
        lambda: supabase.rpc(
            "decrement_inventory",
            {"p_name": supplier_id, "p_item": item, "p_qty": qty},
        ).execute()
    )
    data = response.data
    if data is None:
        return False
    if isinstance(data, list):
        return len(data) > 0
    return True


async def load_initial_map_graph(
    supabase: Client,
) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """
    Args: Supabase client.
    Returns: Tuple of graph adjacency map and hospital-to-node map.
    """
    response = await asyncio.to_thread(
        lambda: supabase.table("hospital_inventory")
        .select("name, x, y")
        .execute()
    )

    rows = response.data or []
    coordinates_by_hospital: dict[str, tuple[float, float]] = {}
    for row in rows:
        coordinates_by_hospital[row["name"]] = (row["x"], row["y"])

    # Sparse graph: only connect hospitals within MAX_EDGE_DISTANCE units.
    # Prevents a complete graph where every route is a direct 2-node hop,
    # ensuring Dijkstra exercises multi-hop path finding during the demo.
    MAX_EDGE_DISTANCE = 5.5

    graph: dict[str, dict[str, float]] = {}
    for hospital_name, (x_coord, y_coord) in coordinates_by_hospital.items():
        graph[hospital_name] = {}
        for neighbor_name, (nx_coord, ny_coord) in coordinates_by_hospital.items():
            if hospital_name == neighbor_name:
                continue
            d = math.dist((x_coord, y_coord), (nx_coord, ny_coord))
            if d <= MAX_EDGE_DISTANCE:
                graph[hospital_name][neighbor_name] = d

    hospital_node_map = {
        hospital_name: hospital_name for hospital_name in coordinates_by_hospital
    }
    return graph, hospital_node_map
