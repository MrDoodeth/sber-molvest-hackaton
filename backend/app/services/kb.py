from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.mappers import document_dto, section_dto
from app.contracts.schemas import (
    KnowledgeDocumentDto,
    KnowledgeDocumentPatch,
    KnowledgeSectionDto,
    KnowledgeSectionPatch,
)
from app.core.constants import PROTECTED_SECTION_IDS
from app.core.enums import CandidateStatus, DocumentSourceType, IndexStatus
from app.core.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.models import (
    Chunk,
    KnowledgeCandidate,
    KnowledgeDocument,
    KnowledgeSection,
    SystemSetting,
)
from app.providers.interfaces import (
    EmbeddingProvider,
    ObjectStorage,
    PermanentDocumentParser,
    StorageError,
    VectorPoint,
    VectorStore,
)
from app.services.attachments import ValidatedUpload, safe_file_name
from app.services.rag_cache import RAG_CACHE_VERSION_KEY
from app.services.tasks import TaskSupervisor

VECTOR_NAMESPACE = uuid.UUID("f72eb19d-0ee1-4f39-924d-7bb9fb8adb76")
logger = logging.getLogger(__name__)


class IngestionFailedError(Exception):
    """Permanent document ingestion did not complete."""


class KnowledgeBaseService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
        parser: PermanentDocumentParser,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        tasks: TaskSupervisor,
        index_concurrency: int = 1,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._parser = parser
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._tasks = tasks
        self._ingestion_gate = asyncio.Semaphore(index_concurrency)
        self._document_locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._scheduled_document_ids: set[uuid.UUID] = set()

    def _lock_for(self, document_id: uuid.UUID) -> asyncio.Lock:
        return self._document_locks.setdefault(document_id, asyncio.Lock())

    def _schedule_ingestion(self, document_id: uuid.UUID) -> None:
        if document_id in self._scheduled_document_ids:
            return
        self._scheduled_document_ids.add(document_id)

        async def run() -> None:
            try:
                await self.ingest(document_id)
            except NotFoundError:
                # The document can be deleted after this task is scheduled.
                # Deletion is terminal and must not be retried by the worker.
                return
            finally:
                self._scheduled_document_ids.discard(document_id)

        self._tasks.spawn(run())

    async def recover_processing_documents(self) -> None:
        """Resume documents whose in-process ingestion was interrupted."""
        async with self._session_factory() as session:
            document_ids = list(
                await session.scalars(
                    select(KnowledgeDocument.id).where(
                        KnowledgeDocument.index_status.in_(
                            [IndexStatus.UPLOADED, IndexStatus.PROCESSING]
                        )
                    )
                )
            )
        for document_id in document_ids:
            self._schedule_ingestion(document_id)

    async def list_sections(self) -> list[KnowledgeSectionDto]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(KnowledgeSection, func.count(KnowledgeDocument.id))
                    .outerjoin(
                        KnowledgeDocument,
                        KnowledgeDocument.section_id == KnowledgeSection.id,
                    )
                    .group_by(KnowledgeSection.id)
                    .order_by(KnowledgeSection.created_at)
                )
            ).all()
            return [
                section_dto(section, int(document_count))
                for section, document_count in rows
            ]

    async def create_section(self, name: str) -> KnowledgeSectionDto:
        async with self._session_factory() as session:
            section = KnowledgeSection(name=name, is_enabled=True)
            session.add(section)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Раздел с таким названием уже существует") from exc
            return section_dto(section)

    async def patch_section(
        self, section_id: uuid.UUID, patch: KnowledgeSectionPatch
    ) -> KnowledgeSectionDto:
        async with self._session_factory() as session:
            section = await session.get(
                KnowledgeSection, section_id, with_for_update=True
            )
            if section is None:
                raise NotFoundError("Раздел базы знаний не найден")
            if section.id in PROTECTED_SECTION_IDS and patch.name is not None:
                raise ConflictError("Системный раздел базы знаний нельзя переименовать")
            old_enabled = section.is_enabled
            if patch.name is not None:
                section.name = patch.name
            if patch.is_enabled is not None:
                section.is_enabled = patch.is_enabled
            documents = (
                await session.scalars(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.section_id == section_id,
                        KnowledgeDocument.index_status == IndexStatus.INDEXED,
                    )
                )
            ).all()
            document_count = int(
                await session.scalar(
                    select(func.count(KnowledgeDocument.id)).where(
                        KnowledgeDocument.section_id == section_id
                    )
                )
                or 0
            )
            updated_payloads: list[KnowledgeDocument] = []
            try:
                await session.flush()
                if patch.is_enabled is not None and patch.is_enabled != old_enabled:
                    for document in documents:
                        await self._vector_store.set_document_payload(
                            document.id,
                            {"is_enabled": section.is_enabled and document.is_enabled},
                        )
                        updated_payloads.append(document)
                    await self._touch_rag_cache_version(session)
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                for document in updated_payloads:
                    try:
                        await self._vector_store.set_document_payload(
                            document.id,
                            {"is_enabled": old_enabled and document.is_enabled},
                        )
                    except Exception:
                        logger.exception(
                            "Unable to compensate section payload for document %s",
                            document.id,
                        )
                raise ConflictError("Раздел с таким названием уже существует") from exc
            except Exception as exc:
                await session.rollback()
                for document in updated_payloads:
                    try:
                        await self._vector_store.set_document_payload(
                            document.id,
                            {"is_enabled": old_enabled and document.is_enabled},
                        )
                    except Exception:
                        logger.exception(
                            "Unable to compensate section payload for document %s",
                            document.id,
                        )
                raise ServiceUnavailableError(
                    "Не удалось обновить раздел в поисковом индексе"
                ) from exc
            return section_dto(section, document_count)

    async def delete_section(self, section_id: uuid.UUID) -> None:
        if section_id in PROTECTED_SECTION_IDS:
            raise ConflictError("Системный раздел базы знаний нельзя удалить")
        async with self._session_factory() as session:
            async with session.begin():
                section = await session.get(
                    KnowledgeSection, section_id, with_for_update=True
                )
                if section is None:
                    raise NotFoundError("Раздел базы знаний не найден")
                document_ids = list(
                    await session.scalars(
                        select(KnowledgeDocument.id).where(
                            KnowledgeDocument.section_id == section_id
                        )
                    )
                )
                for document_id in document_ids:
                    await self.delete_document(document_id)
                # The section row remains locked until all document cleanup has
                # completed, so concurrent uploads cannot orphan storage objects.
                await session.delete(section)
                await self._touch_rag_cache_version(session)

    async def list_documents(
        self, section_id: uuid.UUID | None
    ) -> list[KnowledgeDocumentDto]:
        async with self._session_factory() as session:
            statement = (
                select(KnowledgeDocument, KnowledgeSection)
                .join(
                    KnowledgeSection,
                    KnowledgeDocument.section_id == KnowledgeSection.id,
                )
                .order_by(
                    KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc()
                )
            )
            if section_id is not None:
                statement = statement.where(KnowledgeDocument.section_id == section_id)
            rows = (await session.execute(statement)).all()
            return [document_dto(document, section) for document, section in rows]

    async def get_document(self, document_id: uuid.UUID) -> KnowledgeDocumentDto:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeDocument, KnowledgeSection)
                    .join(
                        KnowledgeSection,
                        KnowledgeDocument.section_id == KnowledgeSection.id,
                    )
                    .where(KnowledgeDocument.id == document_id)
                )
            ).one_or_none()
            if row is None:
                raise NotFoundError("Документ базы знаний не найден")
            return document_dto(row[0], row[1])

    async def read_document(self, document_id: uuid.UUID) -> tuple[bytes, str, str]:
        async with self._session_factory() as session:
            document = await session.get(KnowledgeDocument, document_id)
            if document is None:
                raise NotFoundError("Документ базы знаний не найден")
            storage_key = document.storage_key
            title = document.title

        try:
            data = await self._storage.get(storage_key)
        except StorageError as exc:
            raise ServiceUnavailableError(
                "Хранилище документов временно недоступно"
            ) from exc
        suffix = Path(storage_key).suffix.lower()
        file_name = safe_file_name(f"{title}{suffix}")
        media_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        return data, media_type, file_name

    async def create_document(
        self,
        *,
        upload: ValidatedUpload,
        section_id: uuid.UUID,
        source_type: DocumentSourceType,
        title: str,
        one_c_version: str | None,
        tags: list[str],
        schedule_ingestion: bool = True,
        storage_key: str | None = None,
    ) -> KnowledgeDocumentDto:
        if source_type == DocumentSourceType.RESOLVED_CASE and schedule_ingestion:
            raise ConflictError("resolved_case создаётся только через модерацию")
        key = storage_key or f"knowledge/{upload.sha256}{upload.extension}"
        async with self._session_factory() as session:
            section = await session.get(
                KnowledgeSection, section_id, with_for_update=True
            )
            if section is None:
                raise NotFoundError("Раздел базы знаний не найден")
            duplicate = await session.scalar(
                select(KnowledgeDocument).where(KnowledgeDocument.storage_key == key)
            )
            if duplicate is not None:
                raise ConflictError(
                    "Этот файл уже загружен в базу знаний",
                    {"document_id": str(duplicate.id)},
                )
            try:
                upload.source.seek(0)
                put_file = getattr(self._storage, "put_file", None)
                if callable(put_file):
                    await put_file(key, upload.source, upload.mime_type)
                else:
                    await self._storage.put(key, upload.source.read(), upload.mime_type)
            except StorageError as exc:
                raise ServiceUnavailableError(
                    "Хранилище документов временно недоступно"
                ) from exc
            document = KnowledgeDocument(
                section_id=section_id,
                source_type=source_type,
                title=title.strip(),
                storage_key=key,
                one_c_version=one_c_version,
                tags=tags,
                is_enabled=True,
                index_status=IndexStatus.PROCESSING,
                index_error=None,
            )
            session.add(document)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                duplicate = await session.scalar(
                    select(KnowledgeDocument.id).where(
                        KnowledgeDocument.storage_key == key
                    )
                )
                if duplicate is not None:
                    raise ConflictError(
                        "Этот файл уже загружен в базу знаний",
                        {"document_id": str(duplicate)},
                    ) from exc
                await self._storage.delete(key)
                raise
            except Exception:
                await session.rollback()
                await self._storage.delete(key)
                raise
            result = document_dto(document, section)
        if schedule_ingestion:
            self._schedule_ingestion(document.id)
        return result

    async def patch_document(
        self, document_id: uuid.UUID, patch: KnowledgeDocumentPatch
    ) -> KnowledgeDocumentDto:
        async with self._lock_for(document_id):
            async with self._session_factory() as session:
                document = await session.get(
                    KnowledgeDocument, document_id, with_for_update=True
                )
                if document is None:
                    raise NotFoundError("Документ базы знаний не найден")
                section = await session.get(KnowledgeSection, document.section_id)
                if section is None:
                    raise NotFoundError("Раздел базы знаний не найден")
                if patch.is_enabled is not None:
                    document.is_enabled = patch.is_enabled
                await session.flush()
                if document.index_status == IndexStatus.INDEXED:
                    try:
                        await self._vector_store.set_document_payload(
                            document.id,
                            self._document_payload(document, section),
                        )
                    except Exception as exc:
                        await session.rollback()
                        raise ServiceUnavailableError(
                            "Не удалось обновить документ в поисковом индексе"
                        ) from exc
                await self._touch_rag_cache_version(session)
                await session.commit()
                return document_dto(document, section)

    async def request_reindex(self, document_id: uuid.UUID) -> KnowledgeDocumentDto:
        async with self._lock_for(document_id):
            async with self._session_factory() as session:
                document = await session.get(
                    KnowledgeDocument, document_id, with_for_update=True
                )
                if document is None:
                    raise NotFoundError("Документ базы знаний не найден")
                if document_id not in self._scheduled_document_ids:
                    document.index_status = IndexStatus.PROCESSING
                    document.index_error = None
                    await self._touch_rag_cache_version(session)
                    await session.commit()
        result = await self.get_document(document_id)
        self._schedule_ingestion(document_id)
        return result

    async def ingest(self, document_id: uuid.UUID) -> None:
        async with self._ingestion_gate, self._lock_for(document_id):
            new_vector_ids: list[uuid.UUID] = []
            old_vector_ids: list[uuid.UUID] = []
            try:
                async with self._session_factory() as session:
                    # The row lock covers the complete external indexing flow.
                    # A concurrent delete waits until we either finish indexing
                    # or roll back, then removes the final vector state.
                    async with session.begin():
                        row = (
                            await session.execute(
                                select(KnowledgeDocument, KnowledgeSection)
                                .join(
                                    KnowledgeSection,
                                    KnowledgeDocument.section_id == KnowledgeSection.id,
                                )
                                .where(KnowledgeDocument.id == document_id)
                                .with_for_update()
                            )
                        ).one_or_none()
                        if row is None:
                            raise NotFoundError("Документ базы знаний не найден")
                        document, section = row
                        document.index_status = IndexStatus.PROCESSING
                        document.index_error = None
                        old_vector_ids = list(
                            await session.scalars(
                                select(Chunk.vector_id).where(
                                    Chunk.doc_id == document_id
                                )
                            )
                        )
                        storage_key = document.storage_key
                        suffix = Path(storage_key).suffix

                        data = await self._storage.get(storage_key)
                        temporary_path = await asyncio.to_thread(
                            self._write_temporary, data, suffix
                        )
                        try:
                            parsed_chunks = await self._parser.parse(temporary_path)
                        finally:
                            await asyncio.to_thread(
                                temporary_path.unlink, missing_ok=True
                            )
                        if not parsed_chunks:
                            raise IngestionFailedError(
                                "Документ не содержит текстовых чанков"
                            )
                        contextualized_chunks = [
                            self._contextualize_chunk(
                                document, chunk.text, chunk.heading_path
                            )
                            for chunk in parsed_chunks
                        ]
                        embeddings = await self._embedding_provider.embed_documents(
                            contextualized_chunks
                        )
                        if len(embeddings) != len(parsed_chunks):
                            raise IngestionFailedError(
                                "Embedding provider returned an unexpected vector count"
                            )
                        indexed_at = datetime.now(UTC)
                        points: list[VectorPoint] = []
                        metadata_items: list[dict[str, Any]] = []
                        for index, (parsed, contextualized, embedding) in enumerate(
                            zip(
                                parsed_chunks,
                                contextualized_chunks,
                                embeddings,
                                strict=True,
                            )
                        ):
                            text_digest = hashlib.sha256(
                                contextualized.encode("utf-8")
                            ).hexdigest()
                            vector_id = uuid.uuid5(
                                VECTOR_NAMESPACE,
                                f"{document_id}:{index}:{text_digest}",
                            )
                            new_vector_ids.append(vector_id)
                            metadata = {
                                "heading_path": parsed.heading_path,
                                "page": parsed.page,
                                "chunk_index": index,
                            }
                            metadata_items.append(metadata)
                            payload = {
                                **self._document_payload(document, section),
                                "heading_path": parsed.heading_path,
                                "page": parsed.page,
                                "chunk_index": index,
                                "updated_at": indexed_at.isoformat(),
                                "answer_eligible": True,
                            }
                            points.append(
                                VectorPoint(
                                    vector_id=vector_id,
                                    dense=embedding.dense,
                                    sparse_indices=embedding.sparse_indices,
                                    sparse_values=embedding.sparse_values,
                                    payload=payload,
                                )
                            )
                        await self._vector_store.upsert(points)

                        await session.execute(
                            delete(Chunk).where(Chunk.doc_id == document_id)
                        )
                        session.add_all(
                            [
                                Chunk(
                                    doc_id=document_id,
                                    text=contextualized,
                                    vector_id=vector_id,
                                    metadata_=metadata,
                                )
                                for contextualized, vector_id, metadata in zip(
                                    contextualized_chunks,
                                    new_vector_ids,
                                    metadata_items,
                                    strict=True,
                                )
                            ]
                        )
                        document.index_status = IndexStatus.INDEXED
                        document.index_error = None
                        document.indexed_at = indexed_at
                        await self._touch_rag_cache_version(session)
                        await self._vector_store.set_document_payload(
                            document.id,
                            {
                                "is_enabled": section.is_enabled
                                and document.is_enabled,
                                "answer_eligible": True,
                            },
                        )
                stale_ids = list(set(old_vector_ids) - set(new_vector_ids))
                await self._delete_stale_vectors(stale_ids, document_id)
            except Exception as exc:
                if isinstance(exc, NotFoundError):
                    raise
                introduced = list(set(new_vector_ids) - set(old_vector_ids))
                if introduced:
                    try:
                        await self._vector_store.delete_points(introduced)
                    except Exception:
                        logger.exception(
                            "Unable to compensate vectors for document %s", document_id
                        )
                async with self._session_factory() as session:
                    document = await session.get(KnowledgeDocument, document_id)
                    if document is not None:
                        document.index_status = IndexStatus.FAILED
                        document.index_error = str(exc)[:4000] or type(exc).__name__
                        await session.commit()
                raise IngestionFailedError(str(exc) or type(exc).__name__) from exc

    async def _delete_stale_vectors(
        self, vector_ids: list[uuid.UUID], document_id: uuid.UUID
    ) -> None:
        if not vector_ids:
            return
        for attempt in range(3):
            try:
                await self._vector_store.delete_points(vector_ids)
                return
            except Exception as exc:
                if attempt == 2:
                    logger.exception(
                        "Unable to remove stale vectors for document %s", document_id
                    )
                    raise ServiceUnavailableError(
                        "Не удалось удалить устаревшие векторы документа"
                    ) from exc
                await asyncio.sleep(0.2 * (attempt + 1))

    async def delete_document(self, document_id: uuid.UUID) -> None:
        async with self._lock_for(document_id):
            async with self._session_factory() as session:
                # This is the same row lock used by ingest(). It serializes the
                # whole deletion against active or queued indexing in any worker.
                async with session.begin():
                    document = await session.get(
                        KnowledgeDocument, document_id, with_for_update=True
                    )
                    if document is None:
                        raise NotFoundError("Документ базы знаний не найден")
                    try:
                        await self._vector_store.delete_document(document_id)
                    except Exception as exc:
                        raise ServiceUnavailableError(
                            "Не удалось удалить документ из поискового индекса"
                        ) from exc
                    try:
                        await self._storage.delete(document.storage_key)
                    except Exception as exc:
                        raise ServiceUnavailableError(
                            "Не удалось очистить документ из storage; запись сохранена "
                            "для повторной попытки"
                        ) from exc
                    candidates = list(
                        await session.scalars(
                            select(KnowledgeCandidate)
                            .where(
                                KnowledgeCandidate.resulting_document_id == document_id
                            )
                            .with_for_update()
                        )
                    )
                    # Removing a published document revokes its publication. Do
                    # not leave a candidate claiming that a missing document is
                    # still approved.
                    for candidate in candidates:
                        candidate.status = CandidateStatus.REJECTED
                        candidate.resulting_document_id = None
                    await session.delete(document)
                    await self._touch_rag_cache_version(session)

    @staticmethod
    async def _touch_rag_cache_version(session: AsyncSession) -> None:
        setting = await session.get(
            SystemSetting, RAG_CACHE_VERSION_KEY, with_for_update=True
        )
        if setting is None:
            session.add(SystemSetting(key=RAG_CACHE_VERSION_KEY, value=1))
            return
        try:
            setting.value = int(setting.value) + 1
        except (TypeError, ValueError):
            setting.value = 1

    @staticmethod
    def _write_temporary(data: bytes, suffix: str) -> Path:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            temporary.write(data)
            return Path(temporary.name)

    @staticmethod
    def _document_payload(
        document: KnowledgeDocument, section: KnowledgeSection
    ) -> dict[str, Any]:
        return {
            "document_id": str(document.id),
            "section_id": str(section.id),
            "title": document.title,
            "source_type": document.source_type.value,
            "one_c_version": document.one_c_version,
            "tags": document.tags,
            "is_enabled": section.is_enabled and document.is_enabled,
            "answer_eligible": True,
        }

    @staticmethod
    def _contextualize_chunk(
        document: KnowledgeDocument,
        text: str,
        heading_path: list[str],
    ) -> str:
        context = [f"Документ: {document.title}"]
        if heading_path:
            context.append(f"Раздел: {' > '.join(heading_path)}")
        if document.one_c_version:
            context.append(f"Версия: {document.one_c_version}")
        return "\n".join((*context, "", text.strip()))
