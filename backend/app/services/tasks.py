from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class TaskSupervisor:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[object]] = set()
        self._cancel_on_shutdown: set[asyncio.Task[object]] = set()

    def spawn(
        self,
        awaitable: Coroutine[Any, Any, object],
        *,
        cancel_on_shutdown: bool = False,
    ) -> None:
        task: asyncio.Task[object] = asyncio.create_task(awaitable)
        self._tasks.add(task)
        if cancel_on_shutdown:
            self._cancel_on_shutdown.add(task)
        task.add_done_callback(self._done)

    def _done(self, task: asyncio.Task[object]) -> None:
        self._tasks.discard(task)
        self._cancel_on_shutdown.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "Background task failed",
                exc_info=(type(error), error, error.__traceback__),
            )

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def shutdown(self, grace_seconds: float = 10.0) -> None:
        if not self._tasks:
            return
        for task in tuple(self._cancel_on_shutdown):
            task.cancel()
        if self._cancel_on_shutdown:
            await asyncio.gather(
                *tuple(self._cancel_on_shutdown), return_exceptions=True
            )
        try:
            await asyncio.wait_for(self.drain(), timeout=grace_seconds)
        except TimeoutError:
            for task in tuple(self._tasks):
                task.cancel()
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
