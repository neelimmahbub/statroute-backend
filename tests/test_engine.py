import pytest
from app.routing.engine import compute_shortest_paths, reconstruct_path

MOCK_GRAPH = {
    "A": {"B": 1.0, "C": 4.0},
    "B": {"A": 1.0, "C": 2.0, "D": 5.0},
    "C": {"A": 4.0, "B": 2.0, "D": 1.0},
    "D": {"B": 5.0, "C": 1.0},
}


def test_distances_from_origin():
    distances, _ = compute_shortest_paths("A", MOCK_GRAPH)
    assert distances["A"] == 0.0
    assert distances["B"] == 1.0
    # A→B→C = 1+2 = 3.0 beats A→C = 4.0
    assert distances["C"] == 3.0
    # A→B→C→D = 1+2+1 = 4.0
    assert distances["D"] == 4.0


def test_all_nodes_reachable():
    distances, _ = compute_shortest_paths("A", MOCK_GRAPH)
    assert all(d < float("inf") for d in distances.values())


def test_reconstruct_direct_path():
    _, predecessors = compute_shortest_paths("A", MOCK_GRAPH)
    path = reconstruct_path(predecessors, "A", "B")
    assert path == ["A", "B"]


def test_reconstruct_indirect_path():
    _, predecessors = compute_shortest_paths("A", MOCK_GRAPH)
    path = reconstruct_path(predecessors, "A", "D")
    assert path == ["A", "B", "C", "D"]


def test_reconstruct_same_node():
    _, predecessors = compute_shortest_paths("A", MOCK_GRAPH)
    path = reconstruct_path(predecessors, "A", "A")
    assert path == ["A"]


def test_suppliers_ranked_by_distance():
    # From destination "A", suppliers B and C: B is closer (dist=1) than C (dist=3)
    distances, _ = compute_shortest_paths("A", MOCK_GRAPH)
    suppliers = ["B", "C", "D"]
    ranked = sorted(suppliers, key=lambda s: distances[s])
    assert ranked == ["B", "C", "D"]
