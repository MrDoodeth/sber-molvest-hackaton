from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from itertools import count
from typing import Any


@dataclass(frozen=True, slots=True)
class BrokerEvent:
    event_id: str
    payload: dict[str, Any]


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[BrokerEvent]]] = defaultdict(set)
        self._counter = count(1)
        self._lock = asyncio.Lock()

    async def next_event_id(self) -> str:
        async with self._lock:
            return str(next(self._counter))

    async def publish(self, channel: str, payload: dict[str, Any]) -> BrokerEvent:
        event = BrokerEvent(await self.next_event_id(), _camelize(payload))
        for queue in tuple(self._subscribers.get(channel, ())):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)
        return event

    @asynccontextmanager
    async def subscribe(
        self, channel: str
    ) -> AsyncIterator[asyncio.Queue[BrokerEvent]]:
        queue: asyncio.Queue[BrokerEvent] = asyncio.Queue(maxsize=256)
        self._subscribers[channel].add(queue)
        try:
            yield queue
        finally:
            self._subscribers[channel].discard(queue)
            if not self._subscribers[channel]:
                self._subscribers.pop(channel, None)


def user_dialog_channel(dialog_id: object) -> str:
    return f"user-dialog:{dialog_id}"


def operator_dialog_channel(dialog_id: object) -> str:
    return f"operator-dialog:{dialog_id}"


OPERATOR_QUEUE_CHANNEL = "operator-queue"


def _camelize(value: Any) -> Any:
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    if isinstance(value, dict):
        return {
            re.sub(
                r"_([a-z0-9])",
                lambda match: match.group(1).upper(),
                key,
            ): _camelize(item)
            for key, item in value.items()
        }
    return value


def format_sse(event: BrokerEvent) -> str:
    event_type = str(event.payload.get("type", "message"))
    data = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.event_id}\nevent: {event_type}\ndata: {data}\n\n"


def format_heartbeat(event_id: str) -> str:
    return f"id: {event_id}\n: heartbeat\n\n"
