import asyncio
import json
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

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/events")
async def sse_events():
    async def generator():
        try:
            while True:
                event = await event_bus.get()
                event_type = str(event.get("type", "message"))
                yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
