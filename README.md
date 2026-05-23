# StatRoute

An emergency medical-supply routing engine for hospital networks. Parses unstructured emergency alerts with Gemini, finds the optimal supplier with Reverse Dijkstra, atomically decrements inventory in Supabase, and streams every step to a live operations dashboard over SSE — all wrapped in a circuit breaker, Redis cache, and event bus designed for hackathon-grade chaos demos.

```
┌──────────┐    POST /api/emergency
│ Operator │ ───────────────────────┐
└──────────┘                        ▼
                          ┌─────────────────────┐
                          │  Gemini 1.5 Flash   │  unstructured text → EmergencyRequest
                          │  (with mock safety  │  (hospital, item, qty, urgency, valid)
                          │   net for demo)     │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐         ┌──────────────────┐
                          │ Circuit Breaker     │ open  → │ get_fallback_    │
                          │ (pybreaker, 3-fail) │         │ result(dest)     │
                          └──────────┬──────────┘         └──────────────────┘
                                     │ closed
                          ┌──────────▼──────────┐         ┌──────────────────┐
                          │ Redis cache lookup  │ hit  →  │ atomic decrement │
                          │ (sha256 hash key)   │         │ via Supabase RPC │
                          └──────────┬──────────┘         └──────────────────┘
                                     │ miss
                          ┌──────────▼──────────┐
                          │ Reverse Dijkstra    │  single-source from destination,
                          │ over sparse graph   │  ranks all suppliers by travel time,
                          │ (compute_shortest_  │  fills partial demand greedily
                          │  paths)             │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │ Supabase RPC        │  decrement_inventory + increment_inventory
                          │ (atomic, row-locked │  (rolls back on partial-fulfillment failure)
                          │  decrement)         │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐         ┌──────────────────┐
                          │ pub/sub event bus   │ ───→    │ /events SSE      │
                          │ (per-subscriber Q)  │         │ → live dashboard │
                          └─────────────────────┘         └──────────────────┘
```

---

## Tech Stack

| Layer            | Choice                                     | Why                                          |
|------------------|--------------------------------------------|----------------------------------------------|
| API              | FastAPI 0.115 + Pydantic v2                | Async, type-driven, OpenAPI for free         |
| LLM parser       | Google Gemini 1.5 Flash (`gemini-2.0-flash-lite`) | Cheap structured-JSON extraction      |
| Database         | Supabase (Postgres)                        | RPC for atomic decrements                    |
| Cache            | Redis (async, `redis.asyncio`)             | sub-ms cache hits, 5-minute TTL              |
| Resilience       | pybreaker 1.2                              | Open after 3 fails, manual chaos toggle      |
| Observability    | Sentry SDK (optional)                      | Captures fallback events                     |
| Realtime         | SSE + asyncio.Queue pub/sub                | Per-client queues so every dashboard sees every event |
| Dashboard        | HTMX + Tailwind + animated SVG             | No-build, dispatches and watches in one tab  |
| Container        | Python 3.11-slim, non-root user            | Smallest reproducible footprint              |

---

## Quick Start

### Prerequisites
- Docker Desktop running
- A `.env` file at repo root (see `.env.example`)

```env
GEMINI_API_KEY=AIza...
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=eyJhbGciOi...   # legacy service_role JWT (sb_secret_... is NOT supported by supabase-py 2.9.0)
REDIS_URL=redis://redis:6379
SENTRY_DSN=                   # optional; leave blank to disable
```

### Run

```bash
docker compose up --build
```

Then open `http://localhost:8000/`. The lifespan hook auto-seeds inventory on startup (10 rows: 5 hospitals × 2 items), so the dashboard is demo-ready immediately.

### Stop

```bash
docker compose down
```

---

## Demo Script (90 seconds)

1. **Open the dashboard** at `http://localhost:8000/` — left panel shows live inventory grid, right panel shows the geographic graph and event feed.
2. **Click `Dispatch Route` with the canonical pileup string:**
   `Massive pileup on I-95. St. Jude completely out of O-negative blood, need 10 units immediately!`
   Watch:
   - Gemini parses → animated route from St. Jude to City General
   - Inventory cell for City General drops 50 → 40
   - After ETA elapses, St. Jude inventory increments by 10
3. **Click the red CHAOS button** — circuit breaker badge flips to `OPEN`.
4. **Re-dispatch** the same alert (or use mock #2) — response now carries `"fallback": true` and routes to a pre-computed neighbor; no Dijkstra was called.
5. **Click RESET** — badge returns to `CLOSED`, normal routing resumes.

The three canonical demo strings (matched verbatim in `MOCK_DEMO_RESPONSES`, robust to em-dash / comma swap):

| # | String                                                                                                        | Hospital            | Item               | Qty |
|---|---------------------------------------------------------------------------------------------------------------|---------------------|--------------------|-----|
| 1 | `Massive pileup on I-95. St. Jude completely out of O-negative blood, need 10 units immediately!`             | St. Jude            | O-negative blood   | 10  |
| 2 | `City General reporting critical shortage, need 8 units of epinephrine for incoming trauma cases.`            | City General        | epinephrine        | 8   |
| 3 | `Riverside Medical needs 15 units of O-negative blood for multiple surgeries, high priority.`                 | Riverside Medical   | O-negative blood   | 15  |

---

## API Reference

| Method | Path                          | Purpose                                                                       |
|--------|-------------------------------|-------------------------------------------------------------------------------|
| GET    | `/`                           | Operations dashboard (HTMX + SSE)                                             |
| GET    | `/health`                     | `{"status":"ok"}` for Docker healthcheck                                      |
| GET    | `/events`                     | Server-Sent Events stream (per-subscriber queue)                              |
| GET    | `/api/inventory`              | List all inventory rows                                                       |
| POST   | `/api/inventory/seed/reset`   | DESTRUCTIVE — wipes and re-seeds the canonical 10 rows                        |
| POST   | `/api/emergency`              | Parse alert → route → atomic decrement → SSE broadcast                        |
| POST   | `/api/chaos/toggle`           | Trip the circuit breaker (returns OPEN badge as HTML fragment)                |
| POST   | `/api/chaos/reset`            | Close the circuit breaker (returns CLOSED badge)                              |

### Example: Dispatch from terminal

```powershell
# Form-encoded (works with strict PowerShell quoting)
curl.exe -X POST http://localhost:8000/api/emergency `
  -d "message=Massive pileup on I-95. St. Jude completely out of O-negative blood, need 10 units immediately!"
```

Response:

```json
{
  "routes": [
    {
      "supplier_id": "City General",
      "quantity_allocated": 10,
      "path": ["St. Jude", "City General"],
      "distance": 5.0
    }
  ],
  "total_quantity": 10,
  "partial": false
}
```

### SSE event types broadcast on `/events`

| Type                | When                                                |
|---------------------|-----------------------------------------------------|
| `route_dispatched`  | A new `RouteResult` was computed                    |
| `inventory_updated` | Any inventory row changed                           |
| `in_transit`        | Delivery sim started; carries `eta_seconds`         |
| `delivery_complete` | Inventory increment at destination finished        |
| `circuit_open`      | Breaker tripped (manual or auto)                   |
| `circuit_closed`    | Breaker reset                                      |
| `inventory_snapshot`| Triggered on `/api/inventory` GET                  |

---

## Routing Pipeline (POST `/api/emergency`)

The order is enforced; never reorder:

1. Parse with Gemini → validate with `EmergencyRequest`. On Gemini failure, fall back to `MOCK_DEMO_RESPONSES` lookup; on miss, return clean **422** (no leaked traceback).
2. Resolve `destination_node` from `app.state.hospital_node_map`. **422** if missing.
3. **Circuit-breaker check FIRST** — if `OPEN`, look up the per-destination fallback route, broadcast `circuit_open` + `route_dispatched`, kick off `_simulate_fallback_delivery`, return immediately. (We short-circuit before cache so a flipped breaker never serves stale routes.)
4. Compute SHA-256 cache key from `hospital + item + urgency`. Redis `GET`.
5. **Cache HIT** → try atomic `decrement_inventory`. On success, return cached route. On failure (concurrent depletion), evict and fall through.
6. **Cache MISS** → wrap `compute_shortest_paths` in `breaker.call(...)`. On `CircuitBreakerError`, capture to Sentry and use fallback. Otherwise, rank suppliers by Dijkstra distance, fill demand greedily across multiple suppliers (partial fulfillment), atomically decrement each, **rollback all decrements** on any failure.
7. Cache only single-supplier results (partial routes span multiple inventory states).
8. Publish `route_dispatched`, refreshed `inventory_updated`, kick off `_simulate_delivery`.

---

## Project Structure

```
app/
├── main.py                     # FastAPI app, lifespan hook, /health, /events
├── config.py                   # pydantic-settings, BaseSettings
├── bus.py                      # publish() + subscribe() pub/sub event bus
├── database.py                 # Supabase client singleton
├── agent/
│   ├── schemas.py              # Pydantic v2 models (EmergencyInput, EmergencyRequest, SupplierNode, SupplierRoute, RouteResult)
│   └── services.py             # parse_emergency() — Gemini + mock safety net + tolerant lookup
├── routing/
│   ├── engine.py               # Pure Reverse Dijkstra (compute_shortest_paths, reconstruct_path)
│   ├── circuit.py              # pybreaker wrapper + per-destination fallback routes
│   └── router.py               # POST /api/emergency, /api/chaos/{toggle,reset}, delivery simulation
├── inventory/
│   ├── models.py               # find_supplier, decrement_inventory (atomic RPC), increment_inventory, load_initial_map_graph, reset_seed_data
│   └── router.py               # GET /api/inventory, POST /api/inventory/seed/reset
└── dashboard/
    ├── views.py                # GET / (renders index.html with hospital list)
    └── templates/index.html    # HTMX + Tailwind + animated SVG operations panel
tests/
├── test_engine.py              # 6 unit tests for Dijkstra + path reconstruction
└── test_schemas.py             # 11 unit tests for Pydantic schemas
docs/
├── plan.md                     # Original implementation plan
└── ARCHITECTURE.md             # Module contracts (single source of truth)
```

---

## Key Design Decisions

**Reverse Dijkstra, not forward.** We run single-source shortest-path *from the destination outward*. Every supplier's distance falls out of one Dijkstra pass, ranking is `O(n log n)` after that, and partial fulfillment ("two suppliers can each ship 5 of the 10 units") works in one query. Forward Dijkstra would require N runs.

**Sparse graph, not complete.** `load_initial_map_graph` only connects hospitals within `MAX_EDGE_DISTANCE = 5.5` units. A complete graph would mean every shortest path is a 2-node hop and Dijkstra never gets exercised — the sparse edges force at least some 3-node paths in the demo.

**Atomic decrement via Postgres RPC.** Every inventory mutation goes through `decrement_inventory(p_name, p_item, p_qty)` which is a single SQL statement with row-level locking. Returning `False` (zero rows updated) is the contract for "out of stock" or "concurrent depletion." Python never does read-modify-write — that would be a TOCTOU race under concurrent load.

**Circuit-check before cache.** A flipped breaker MUST short-circuit everything, including cache reads. Otherwise an "OPEN" demo would still serve happy-path responses out of Redis and the failure mode would never be visible.

**Per-subscriber pub/sub bus.** A single `asyncio.Queue` would deliver each event to *one* SSE client (whichever popped first). The `subscribe()` context manager creates a per-connection queue and `publish()` fans out, so every open dashboard tab sees every event. Bounded at `maxsize=1000` per subscriber.

**Mock fallback in `parse_emergency`.** Gemini's free tier hits 429 quickly during a live demo. The function catches *any* exception, normalizes dashes/punctuation, and matches against three canonical demo strings. Failure on a non-canonical string returns a clean **422**, never a 500 with a traceback.

**Optional schema fields with `Field(ge=0)`.** Fallback routes carry `quantity_allocated=0` until the router fills them in. `ge=0` (not `gt=0`) keeps the schema permissive enough for fallback while still rejecting negatives.

---

## Tests

```bash
docker compose exec web pytest tests/ -v
```

```
17 passed in 3.5s
```

| File              | Coverage                                                                     |
|-------------------|------------------------------------------------------------------------------|
| `test_engine.py`  | 6 tests: distances, reachability, direct/indirect/same-node path, ranking    |
| `test_schemas.py` | 11 tests: input/request distinct types, urgency Literal, quantity validation, partial route shape |

External dependencies (Gemini, Supabase, Redis) are not mocked here — they are exercised in the live smoke tests run against the docker-compose stack.

---

## Known Limitations & Production Gaps

- **Gemini free tier is rate-limited.** Once `generate_content_free_tier_requests` quota is exhausted, only the 3 canonical demo strings work. Production would use a paid key, retry-with-backoff, and a richer mock catalogue.
- **JSON body to `/api/emergency` is fragile** because the endpoint also has `Form(...)` parameters; FastAPI's body parser becomes ambiguous. Use form-encoded (`-d "message=..."`) — this is what the dashboard does.
- **Circuit breaker manual reset only.** `reset_timeout = 3600s` so a tripped breaker stays open until an operator clicks RESET. Intentional for demo control.
- **Sparse graph is hand-tuned.** `MAX_EDGE_DISTANCE = 5.5` was chosen so the seed coordinates produce at least one multi-hop shortest path; production would derive this from real road-network geometry.
- **No auth.** The dashboard's "Switch Terminal" identity gate is enforced server-side (`selected_hospital` form field) but is trivially spoofable. Production needs real session auth.
- **Inventory rebuild is destructive.** `POST /api/inventory/seed/reset` wipes and re-inserts the seed rows. Useful for live demo recovery; never call in production.

---

## Operational Tips for the Demo

- **Reset to a clean state between scenarios:** `curl.exe -X POST http://localhost:8000/api/inventory/seed/reset` (or just restart the container — lifespan hook re-seeds).
- **Tail logs:** `docker compose logs -f web`
- **Verify the breaker state via the badge** in the dashboard top-right; chaos toggle returns the badge HTML directly (HTMX-friendly).
- **The em-dash gotcha:** mock string #2 originally used `—`. The fallback lookup now normalizes `—`/`–` to `,` and strips trailing punctuation, so any reasonable variation matches.

---

## License & Credits

Built for a hackathon. No license — treat as a teaching artifact, not production code.
