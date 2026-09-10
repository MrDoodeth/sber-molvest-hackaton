from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

GIGACHAT_ADVISORY_LOCK_KEY = 712031044


class GenerationGate:
    """Serialize GigaChat requests in-process and across PostgreSQL workers.

    The gate is re-entrant for the current asyncio task so a complete atomic
    turn can hold it while provider methods guard their individual calls too.
    """

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self._engine = engine
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
            if self._engine is None or self._engine.dialect.name != "postgresql":
                yield
            else:
                async with self._engine.connect() as connection:
                    await connection.execute(
                        text("SELECT pg_advisory_lock(:lock_key)"),
                        {"lock_key": GIGACHAT_ADVISORY_LOCK_KEY},
                    )
                    try:
                        yield
                    finally:
                        await connection.execute(
                            text("SELECT pg_advisory_unlock(:lock_key)"),
                            {"lock_key": GIGACHAT_ADVISORY_LOCK_KEY},
                        )
        finally:
            self._depth.reset(token)
            self._semaphore.release()
