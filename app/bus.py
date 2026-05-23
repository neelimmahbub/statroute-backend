import asyncio
from contextlib import asynccontextmanager

_subscribers: list[asyncio.Queue] = []


async def publish(event: dict) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


@asynccontextmanager
async def subscribe():
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.append(q)
    try:
        yield q
    finally:
        if q in _subscribers:
            _subscribers.remove(q)
