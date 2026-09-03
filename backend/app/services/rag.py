from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.schemas import SourceRef
from app.core.enums import IndexStatus
from app.models import Chunk, KnowledgeDocument, KnowledgeSection
from app.providers.interfaces import (
    EmbeddingProvider,
    Evidence,
    HybridEmbedding,
    VectorHit,
    VectorStore,
)

RAGStatus = Literal["ready", "empty", "no_match"]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    evidence: list[Evidence]
    status: RAGStatus


class RAGService:
    def __init__(
        self, embedding_provider: EmbeddingProvider, vector_store: VectorStore
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    async def embed_query(self, search_context: str) -> HybridEmbedding:
        return await self._embedding_provider.embed_query(search_context)

    async def retrieve(
        self, session: AsyncSession, search_context: str, top_k: int
    ) -> list[Evidence]:
        query = await self.embed_query(search_context)
        result = await self.retrieve_embeddings(session, [query], top_k)
        return result.evidence

    async def retrieve_embeddings(
        self,
        session: AsyncSession,
        queries: list[HybridEmbedding],
        top_k: int,
        weights: list[float] | None = None,
    ) -> RetrievalResult:
        if not queries or top_k < 1:
            return RetrievalResult([], await self._empty_status(session))

        candidate_limit = max(top_k * 4, 20)
        hit_lists = await asyncio.gather(
            *(self._vector_store.search(query, candidate_limit) for query in queries)
        )
        hits = self._fuse_hits(hit_lists, weights)
        if not hits:
            return RetrievalResult([], await self._empty_status(session))

        vector_ids = [hit.vector_id for hit in hits]
        rows = (
            await session.execute(
                select(Chunk, KnowledgeDocument, KnowledgeSection)
                .join(KnowledgeDocument, Chunk.doc_id == KnowledgeDocument.id)
                .join(
                    KnowledgeSection,
                    KnowledgeDocument.section_id == KnowledgeSection.id,
                )
                .where(
                    Chunk.vector_id.in_(vector_ids),
                    KnowledgeDocument.is_enabled.is_(True),
                    KnowledgeSection.is_enabled.is_(True),
                    KnowledgeDocument.index_status == IndexStatus.INDEXED,
                )
            )
        ).all()
        by_vector = {chunk.vector_id: (chunk, document) for chunk, document, _ in rows}
        evidence: list[Evidence] = []
        for hit in hits:
            row = by_vector.get(hit.vector_id)
            if row is None:
                continue
            chunk, document = row
            label = f"S{len(evidence) + 1}"
            evidence.append(
                Evidence(
                    source=SourceRef(
                        document_id=document.id,
                        title=document.title,
                        label=label,
                    ),
                    text=chunk.text,
                )
            )
            if len(evidence) == top_k:
                break
        if not evidence:
            return RetrievalResult([], await self._empty_status(session))
        return RetrievalResult(evidence, "ready")

    @staticmethod
    def _fuse_hits(
        hit_lists: list[list[VectorHit]], weights: list[float] | None
    ) -> list[VectorHit]:
        if weights is None:
            weights = [1.0] * len(hit_lists)
        if len(weights) != len(hit_lists):
            raise ValueError("RAG query weights must match query count")

        fused_scores: dict[uuid.UUID, float] = {}
        for weight, hits in zip(weights, hit_lists, strict=True):
            if weight <= 0:
                continue
            for rank, hit in enumerate(hits, start=1):
                fused_scores[hit.vector_id] = fused_scores.get(hit.vector_id, 0.0) + (
                    weight / (60.0 + rank)
                )

        ordered = sorted(
            fused_scores.items(), key=lambda item: (-item[1], str(item[0]))
        )
        return [
            VectorHit(vector_id=vector_id, score=score) for vector_id, score in ordered
        ]

    async def _empty_status(self, session: AsyncSession) -> RAGStatus:
        indexed_chunks = await session.scalar(
            select(func.count(Chunk.id))
            .join(KnowledgeDocument, Chunk.doc_id == KnowledgeDocument.id)
            .join(
                KnowledgeSection,
                KnowledgeDocument.section_id == KnowledgeSection.id,
            )
            .where(
                KnowledgeDocument.is_enabled.is_(True),
                KnowledgeSection.is_enabled.is_(True),
                KnowledgeDocument.index_status == IndexStatus.INDEXED,
            )
        )
        return "empty" if not indexed_chunks else "no_match"
