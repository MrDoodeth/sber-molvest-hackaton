from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Request

from app.services.broker import BrokerEvent, EventBroker, format_heartbeat, format_sse


async def event_stream(
    request: Request,
    broker: EventBroker,
    channel: str,
    heartbeat_seconds: float,
    initial_payload: dict[str, object] | None = None,
) -> AsyncIterator[str]:
    async with broker.subscribe(channel) as queue:
        if initial_payload is not None:
            yield format_sse(BrokerEvent(await broker.next_event_id(), initial_payload))
        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except TimeoutError:
                yield format_heartbeat(await broker.next_event_id())
                continue
            yield format_sse(event)


async def operator_dialog_event_stream(
    request: Request,
    broker: EventBroker,
    channel: str,
    heartbeat_seconds: float,
    operator_id: str,
    has_access: Callable[[], Awaitable[bool]],
    initial_payload: dict[str, object] | None = None,
) -> AsyncIterator[str]:
    """Stream a dialog until its assignment no longer permits access."""
    async with broker.subscribe(channel) as queue:
        if initial_payload is not None:
            yield format_sse(BrokerEvent(await broker.next_event_id(), initial_payload))
        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except TimeoutError:
                if not await has_access():
                    return
                yield format_heartbeat(await broker.next_event_id())
                continue

            if event.payload.get("type") == "operator_access_revoked":
                operator = event.payload.get("operator")
                assigned_id = operator.get("id") if isinstance(operator, dict) else None
                if assigned_id != operator_id:
                    yield format_sse(event)
                    return
                continue
            if event.payload.get("type") == "dialog_closed":
                yield format_sse(event)
                return
            if not await has_access():
                return
            yield format_sse(event)


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
