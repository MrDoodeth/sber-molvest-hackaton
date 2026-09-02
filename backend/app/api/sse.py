from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import Request

from app.services.broker import EventBroker, format_heartbeat, format_sse


async def event_stream(
    request: Request,
    broker: EventBroker,
    channel: str,
    heartbeat_seconds: float,
) -> AsyncIterator[str]:
    async with broker.subscribe(channel) as queue:
        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except TimeoutError:
                yield format_heartbeat(await broker.next_event_id())
                continue
            yield format_sse(event)


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
