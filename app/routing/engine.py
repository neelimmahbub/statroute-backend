import heapq


def compute_shortest_paths(
    origin: str,
    graph: dict[str, dict[str, float]],
) -> tuple[dict[str, float], dict[str, str | None]]:
    """
    Single-source Dijkstra from origin over a weighted adjacency graph.

    Reverse Dijkstra: caller passes the requesting hospital (destination of
    delivery) as origin. One run produces shortest distances from origin to
    every node, enabling O(1) distance lookups when ranking suppliers and
    accumulating top candidates for partial fulfillment — without a
    per-supplier Dijkstra.

    Returns:
        distances: every node mapped to its shortest distance from origin
                   (float('inf') if unreachable, 0.0 for origin itself).
        predecessors: every node mapped to its prior node on the shortest
                      path from origin (None for origin and unreachable nodes).
    """
    distances: dict[str, float] = {node: float("inf") for node in graph}
    predecessors: dict[str, str | None] = {node: None for node in graph}
    distances[origin] = 0.0

    heap: list[tuple[float, str]] = [(0.0, origin)]
    while heap:
        current_dist, current = heapq.heappop(heap)
        if current_dist > distances[current]:
            continue
        for neighbor, weight in graph.get(current, {}).items():
            distance = current_dist + weight
            if distance < distances[neighbor]:
                distances[neighbor] = distance
                predecessors[neighbor] = current
                heapq.heappush(heap, (distance, neighbor))

    return distances, predecessors


def reconstruct_path(
    predecessors: dict[str, str | None],
    origin: str,
    target: str,
) -> list[str]:
    """
    Walk the predecessors map backward from target to origin, returning the
    ordered node list. Returns [origin] when origin == target.
    """
    if origin == target:
        return [origin]

    path: list[str] = []
    current: str | None = target
    while current is not None:
        path.append(current)
        current = predecessors.get(current)
    path.reverse()
    return path
