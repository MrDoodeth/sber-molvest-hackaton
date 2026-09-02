from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.schemas import SourceRef
from app.models import Chunk, KnowledgeDocument, KnowledgeSection
from app.providers.interfaces import EmbeddingProvider, Evidence, VectorStore


class RAGService:
    def __init__(
        self, embedding_provider: EmbeddingProvider, vector_store: VectorStore
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    async def retrieve(
        self, session: AsyncSession, search_context: str, top_k: int
    ) -> list[Evidence]:
        query = await self._embedding_provider.embed_query(search_context)
        hits = await self._vector_store.search(query, top_k)
        if not hits:
            return []
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
        return evidence
