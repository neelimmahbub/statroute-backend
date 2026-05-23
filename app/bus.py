import asyncio

event_bus: asyncio.Queue = asyncio.Queue(maxsize=1000)
