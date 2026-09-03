from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.core.config import EMBEDDING_DIMENSION, QDRANT_COLLECTION
from app.providers.interfaces import (
    HybridEmbedding,
    VectorHit,
    VectorPoint,
    VectorStoreError,
)


class QdrantHybridVectorStore:
    def __init__(self, url: str, api_key: str | None = None) -> None:
        self._url = url
        self._api_key = api_key
        self._client: Any | None = None
        self._collection_ready = False
        self._ready_lock = asyncio.Lock()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from qdrant_client import AsyncQdrantClient
        except ImportError as exc:
            raise VectorStoreError("qdrant-client is required for retrieval") from exc
        self._client = AsyncQdrantClient(url=self._url, api_key=self._api_key)
        return self._client

    async def ensure_collection(self) -> None:
        if self._collection_ready:
            return
        async with self._ready_lock:
            if self._collection_ready:
                return
            try:
                from qdrant_client.models import (
                    Distance,
                    SparseIndexParams,
                    SparseVectorParams,
                    VectorParams,
                )

                client = self._get_client()
                if not await client.collection_exists(QDRANT_COLLECTION):
                    await client.create_collection(
                        collection_name=QDRANT_COLLECTION,
                        vectors_config={
                            "dense": VectorParams(
                                size=EMBEDDING_DIMENSION, distance=Distance.COSINE
                            )
                        },
                        sparse_vectors_config={
                            "sparse": SparseVectorParams(
                                index=SparseIndexParams(on_disk=False)
                            )
                        },
                    )
                self._collection_ready = True
            except VectorStoreError:
                raise
            except Exception as exc:
                raise VectorStoreError(
                    "Unable to initialize Qdrant collection"
                ) from exc

    async def upsert(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        await self.ensure_collection()
        try:
            from qdrant_client.models import PointStruct, SparseVector

            qdrant_points = [
                PointStruct(
                    id=str(point.vector_id),
                    vector={
                        "dense": point.dense,
                        "sparse": SparseVector(
                            indices=point.sparse_indices,
                            values=point.sparse_values,
                        ),
                    },
                    payload=point.payload,
                )
                for point in points
            ]
            await self._get_client().upsert(
                collection_name=QDRANT_COLLECTION,
                points=qdrant_points,
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError("Unable to upsert knowledge vectors") from exc

    async def search(self, query: HybridEmbedding, limit: int) -> list[VectorHit]:
        await self.ensure_collection()
        try:
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                Fusion,
                FusionQuery,
                MatchValue,
                Prefetch,
                SparseVector,
            )

            prefetch_limit = max(limit * 4, 20)
            response = await self._get_client().query_points(
                collection_name=QDRANT_COLLECTION,
                prefetch=[
                    Prefetch(query=query.dense, using="dense", limit=prefetch_limit),
                    Prefetch(
                        query=SparseVector(
                            indices=query.sparse_indices,
                            values=query.sparse_values,
                        ),
                        using="sparse",
                        limit=prefetch_limit,
                    ),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                query_filter=Filter(
                    must=[
                        FieldCondition(key="is_enabled", match=MatchValue(value=True)),
                    ]
                ),
                limit=limit,
                with_payload=False,
            )
            return [
                VectorHit(vector_id=uuid.UUID(str(point.id)), score=float(point.score))
                for point in response.points
            ]
        except Exception as exc:
            raise VectorStoreError("Qdrant hybrid retrieval failed") from exc

    async def delete_points(self, vector_ids: list[uuid.UUID]) -> None:
        if not vector_ids:
            return
        await self.ensure_collection()
        try:
            from qdrant_client.models import PointIdsList

            await self._get_client().delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=PointIdsList(
                    points=[str(vector_id) for vector_id in vector_ids]
                ),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError("Unable to delete knowledge vectors") from exc

    async def delete_document(self, document_id: uuid.UUID) -> None:
        await self.ensure_collection()
        try:
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                FilterSelector,
                MatchValue,
            )

            await self._get_client().delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="document_id",
                                match=MatchValue(value=str(document_id)),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError("Unable to delete document vectors") from exc

    async def set_document_payload(
        self, document_id: uuid.UUID, payload: dict[str, Any]
    ) -> None:
        await self.ensure_collection()
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            await self._get_client().set_payload(
                collection_name=QDRANT_COLLECTION,
                payload=payload,
                points=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=str(document_id)),
                        )
                    ]
                ),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError("Unable to update document vector payload") from exc
