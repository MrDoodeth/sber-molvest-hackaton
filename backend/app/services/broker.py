from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from itertools import count
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BrokerEvent:
    event_id: str
    payload: dict[str, Any]


class EventBroker:
    def __init__(
        self,
        redis_url: str | None = None,
        *,
        connect_timeout_seconds: float = 2.0,
        socket_timeout_seconds: float = 2.0,
    ) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[BrokerEvent]]] = defaultdict(set)
        self._counter = count(1)
        self._instance_id = uuid.uuid4().hex
        self._lock = asyncio.Lock()
        self._redis = (
            Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=connect_timeout_seconds,
                socket_timeout=socket_timeout_seconds,
            )
            if redis_url
            else None
        )
        self._listener_task: asyncio.Task[None] | None = None
        self._closing = False
        self._ready = asyncio.Event()

    async def start(self) -> None:
        if self._redis is None or self._listener_task is not None:
            return
        await self._redis.ping()
        self._listener_task = asyncio.create_task(self._listen())
        await asyncio.wait_for(self._ready.wait(), timeout=5)

    async def close(self) -> None:
        self._closing = True
        if self._listener_task is not None:
            self._listener_task.cancel()
            await asyncio.gather(self._listener_task, return_exceptions=True)
            self._listener_task = None
        if self._redis is not None:
            await self._redis.aclose()

    async def next_event_id(self) -> str:
        async with self._lock:
            return f"{self._instance_id}:{next(self._counter)}"

    async def publish(self, channel: str, payload: dict[str, Any]) -> BrokerEvent:
        event = BrokerEvent(await self.next_event_id(), _camelize(payload))
        if self._redis is not None:
            try:
                await self._redis.publish(
                    channel,
                    json.dumps(
                        {"event_id": event.event_id, "payload": event.payload},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                return event
            except Exception:
                logger.exception("Redis event publish failed; using local delivery")
        self._fan_out(channel, event)
        return event

    def _fan_out(self, channel: str, event: BrokerEvent) -> None:
        for queue in tuple(self._subscribers.get(channel, ())):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    async def _listen(self) -> None:
        assert self._redis is not None
        while not self._closing:
            pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
            try:
                await pubsub.subscribe(OPERATOR_QUEUE_CHANNEL)
                await pubsub.psubscribe("user-dialog:*", "operator-dialog:*")
                self._ready.set()
                while not self._closing:
                    message = await pubsub.get_message(timeout=1.0)
                    if message is None:
                        continue
                    channel = message.get("channel")
                    data = message.get("data")
                    if not isinstance(channel, str) or not isinstance(data, str):
                        continue
                    envelope = json.loads(data)
                    event_id = envelope.get("event_id")
                    payload = envelope.get("payload")
                    if isinstance(event_id, str) and isinstance(payload, dict):
                        self._fan_out(channel, BrokerEvent(event_id, payload))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Redis event broker listener failed; reconnecting")
                await asyncio.sleep(1)
            finally:
                await pubsub.aclose()

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
