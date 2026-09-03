from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar


class GenerationGate:
    """Serialize every GigaChat request in one backend process.

    The gate is re-entrant for the current asyncio task so a complete atomic
    turn can hold it while provider methods guard their individual calls too.
    """

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(1)
        self._depth: ContextVar[int] = ContextVar(
            "gigachat_generation_gate_depth", default=0
        )

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        depth = self._depth.get()
        if depth:
            token = self._depth.set(depth + 1)
            try:
                yield
            finally:
                self._depth.reset(token)
            return

        await self._semaphore.acquire()
        token = self._depth.set(1)
        try:
            yield
        finally:
            self._depth.reset(token)
            self._semaphore.release()
