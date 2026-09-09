from __future__ import annotations

import json
import logging
import uuid

from redis.asyncio import Redis

from app.providers.interfaces import VectorHit

logger = logging.getLogger(__name__)
RAG_CACHE_VERSION_KEY = "rag_cache_version"


class RAGCache:
    def __init__(self, url: str | None, ttl_seconds: int) -> None:
        self._client = Redis.from_url(url, decode_responses=True) if url else None
        self._ttl_seconds = ttl_seconds

    async def get(self, key: str) -> list[VectorHit] | None:
        if self._client is None:
            return None
        try:
            raw = await self._client.get(key)
            if raw is None:
                return None
            payload = json.loads(raw)
            if not isinstance(payload, list):
                return None
            return [
                VectorHit(vector_id=uuid.UUID(item[0]), score=float(item[1]))
                for item in payload
                if isinstance(item, list)
                and len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], int | float)
            ]
        except Exception:
            logger.warning("RAG cache read failed; using Qdrant", exc_info=True)
            return None

    async def set(self, key: str, hits: list[VectorHit]) -> None:
        if self._client is None:
            return
        payload = json.dumps([[str(hit.vector_id), hit.score] for hit in hits])
        try:
            await self._client.set(key, payload, ex=self._ttl_seconds)
        except Exception:
            logger.warning("RAG cache write failed", exc_info=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
