from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Hashable
from contextlib import asynccontextmanager


class KeyedLockRegistry:
    """Keeps per-resource locks only while a caller is using or waiting for one."""

    def __init__(self) -> None:
        self._entries: dict[Hashable, tuple[asyncio.Lock, int]] = {}
        self._registry_lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, key: Hashable) -> AsyncIterator[None]:
        async with self._registry_lock:
            lock, users = self._entries.get(key, (asyncio.Lock(), 0))
            self._entries[key] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            async with self._registry_lock:
                current_lock, users = self._entries[key]
                if users == 1:
                    del self._entries[key]
                else:
                    self._entries[key] = (current_lock, users - 1)
