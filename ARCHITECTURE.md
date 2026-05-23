<!-- CURSOR: Read this entire file before implementing. Follow patterns exactly. -->

# StatRoute — Architecture Reference

## Stack
- FastAPI 3.11+ (async, Pydantic v2)
- Gemini 1.5 Flash via google-generativeai async
- Supabase (PostgreSQL) via supabase-py
- Redis via redis.asyncio (always access as request.app.state.redis)
- pybreaker 1.2+ (CircuitBreaker on routing engine)
- sentry-sdk[fastapi] (middleware auto-capture + explicit captures)
- Jinja2 + vanilla JS EventSource (SSE dashboard)

## Critical Patterns

### EventBus
```python
from app.bus import event_bus
await event_bus.put({"type": "route_dispatched", "path": path})
```
Never define asyncio.Queue inline. Always import from app.bus.

### Redis access
```python
redis = request.app.state.redis  # in every router endpoint
```
Never import redis directly in routers.

### App state (loaded once at startup)
```python
request.app.state.static_network_graph  # dict[str, dict[str, float]]
request.app.state.hospital_node_map     # dict[str, str] — name → node key
```

### Pydantic v2
Use `.model_dump()` not `.dict()`. Use `model_validate()` not `parse_obj()`.

### Atomic inventory decrement
Handled via Supabase RPC `decrement_inventory(p_name, p_item, p_qty)`.
Returns updated rows — empty list = 0 rowcount = False.

## Module Contracts

### app/agent/schemas.py
```python
class EmergencyInput(BaseModel):
    message: str

class EmergencyRequest(BaseModel):
    hospital: str
    item: str
    quantity: int
    urgency: Literal["Critical", "High", "Medium"]

class SupplierNode(BaseModel):
    id: str       # hospital name (= graph node key)
    node: str     # same as id
    available_qty: int
    x: float
    y: float

class PathResult(BaseModel):
    path: list[str]
    total_distance: float
```

### app/routing/engine.py
```python
def compute_path(origin: str, destination: str, graph: dict[str, dict[str, float]]) -> PathResult:
```
Pure function. No I/O. No side effects. Graph nodes are hospital name strings.

### app/routing/circuit.py
```python
breaker: pybreaker.CircuitBreaker  # fail_max=3, reset_timeout=30
STATIC_FALLBACK_PATH: dict         # {"path": [...], "total_distance": 0.0, "fallback": True}
def toggle_breaker() -> None
def reset_breaker() -> None
```

### POST /api/emergency signature
```python
async def route_emergency(body: EmergencyInput, request: Request) -> dict
```

## Dual-Agent Workflow
- Claude Code: Phases 1 and 5 (infrastructure, polish, git orchestration)
- Cursor Agent: Phases 2-4 (module implementation, one file at a time)
- Git commit = handoff boundary. Never edit the same file in both tools simultaneously.
