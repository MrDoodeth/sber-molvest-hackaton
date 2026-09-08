from __future__ import annotations

import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path

from app.core.database import create_database
from app.core.enums import (
    CandidateSource,
    CandidateStatus,
    DocumentSourceType,
    IndexStatus,
    UserRole,
)
from app.models import (
    Base,
    Dialog,
    KnowledgeCandidate,
    KnowledgeDocument,
    KnowledgeSection,
    User,
)
from app.services.kb import KnowledgeBaseService
from app.services.tasks import TaskSupervisor
from sqlalchemy import select


class FakeStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted: list[uuid.UUID] = []

    async def delete_document(self, document_id: uuid.UUID) -> None:
        self.deleted.append(document_id)


class KnowledgeDeletionTests(unittest.TestCase):
    def test_delete_removes_storage_and_prevents_queued_reindex(self) -> None:
        asyncio.run(self._delete_removes_storage_and_prevents_queued_reindex())

    async def _delete_removes_storage_and_prevents_queued_reindex(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "knowledge.db"
            engine, session_factory = create_database(
                f"sqlite+aiosqlite:///{database_path}"
            )
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            document_id = uuid.uuid4()
            storage_key = "knowledge/deletion-test.pdf"
            async with session_factory() as session:
                section = KnowledgeSection(name="Удаление")
                session.add(section)
                user = User(role=UserRole.USER, display_name="Пользователь")
                session.add(user)
                await session.flush()
                dialog = Dialog(user_id=user.id)
                session.add(dialog)
                await session.flush()
                document = KnowledgeDocument(
                    id=document_id,
                    section_id=section.id,
                    source_type=DocumentSourceType.INTERNAL_KB,
                    title="Удаляемый документ",
                    storage_key=storage_key,
                    is_enabled=True,
                    index_status=IndexStatus.PROCESSING,
                )
                session.add(document)
                await session.flush()
                session.add(
                    KnowledgeCandidate(
                        dialog_id=dialog.id,
                        source=CandidateSource.ADMIN,
                        generated_card={"title": "Кейс"},
                        status=CandidateStatus.APPROVED,
                        resulting_document_id=document_id,
                    )
                )
                await session.commit()

            storage = FakeStorage()
            vector_store = FakeVectorStore()
            tasks = TaskSupervisor()
            service = KnowledgeBaseService(
                session_factory=session_factory,
                storage=storage,  # type: ignore[arg-type]
                parser=object(),  # type: ignore[arg-type]
                embedding_provider=object(),  # type: ignore[arg-type]
                vector_store=vector_store,  # type: ignore[arg-type]
                tasks=tasks,
            )

            await service.delete_document(document_id)
            service._schedule_ingestion(document_id)
            await tasks.drain()

            self.assertEqual(vector_store.deleted, [document_id])
            self.assertEqual(storage.deleted, [storage_key])
            async with session_factory() as session:
                self.assertIsNone(await session.get(KnowledgeDocument, document_id))
                candidate = await session.scalar(select(KnowledgeCandidate))
                self.assertEqual(candidate.status, CandidateStatus.REJECTED)
                self.assertIsNone(candidate.resulting_document_id)

            await engine.dispose()
