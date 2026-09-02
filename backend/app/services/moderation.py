from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.mappers import candidate_dto, feedback_dto
from app.contracts.schemas import (
    CaseCard,
    FeedbackDto,
    KnowledgeCandidateDto,
)
from app.core.constants import DEFAULT_CASE_SECTION_ID
from app.core.enums import (
    CandidateSource,
    CandidateStatus,
    DialogStatus,
    DocumentSourceType,
    FeedbackVerdict,
    MessageAuthor,
    UserRole,
)
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.models import (
    Attachment,
    Dialog,
    DialogFeedback,
    KnowledgeCandidate,
    KnowledgeDocument,
    KnowledgeSection,
    Message,
    User,
)
from app.providers.interfaces import ProviderError, StorageError
from app.services.attachments import AttachmentService, ValidatedUpload
from app.services.kb import IngestionFailedError, KnowledgeBaseService
from app.services.settings import SettingsService

logger = logging.getLogger(__name__)


class ModerationService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        knowledge_base: KnowledgeBaseService,
        attachment_service: AttachmentService,
        settings_service: SettingsService,
    ) -> None:
        self._session_factory = session_factory
        self._knowledge_base = knowledge_base
        self._attachment_service = attachment_service
        self._settings_service = settings_service
        self._candidate_locks: dict[uuid.UUID, asyncio.Lock] = {}

    def _lock_for(self, candidate_id: uuid.UUID) -> asyncio.Lock:
        return self._candidate_locks.setdefault(candidate_id, asyncio.Lock())

    async def add_feedback(
        self, user: User, dialog_id: uuid.UUID, verdict: FeedbackVerdict
    ) -> tuple[FeedbackDto, KnowledgeCandidateDto | None]:
        if user.role != UserRole.USER:
            raise ForbiddenError("Оценку оставляет только пользователь")
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id, with_for_update=True)
            if dialog is None:
                raise NotFoundError("Диалог не найден")
            if dialog.user_id != user.id:
                raise ForbiddenError()
            if dialog.status != DialogStatus.CLOSED:
                raise ConflictError("Оценка доступна только после закрытия тикета")
            existing = await session.scalar(
                select(DialogFeedback).where(DialogFeedback.dialog_id == dialog_id)
            )
            if existing is not None:
                if existing.verdict != verdict:
                    raise ConflictError("Итоговая оценка уже сохранена")
                candidate = None
                if verdict == FeedbackVerdict.HELPFUL:
                    candidate = await self._create_or_get_candidate(
                        session, dialog_id, CandidateSource.USER_FEEDBACK
                    )
                    await session.commit()
                return feedback_dto(existing), (
                    await self._candidate_with_reviewer(session, candidate)
                    if candidate
                    else None
                )
            feedback = DialogFeedback(dialog_id=dialog_id, verdict=verdict)
            try:
                async with session.begin_nested():
                    session.add(feedback)
                    await session.flush()
            except IntegrityError as exc:
                concurrent = await session.scalar(
                    select(DialogFeedback).where(DialogFeedback.dialog_id == dialog_id)
                )
                if concurrent is None:
                    raise ConflictError("Не удалось сохранить итоговую оценку") from exc
                if concurrent.verdict != verdict:
                    raise ConflictError("Итоговая оценка уже сохранена") from exc
                feedback = concurrent
            candidate = None
            if verdict == FeedbackVerdict.HELPFUL:
                candidate = await self._create_or_get_candidate(
                    session, dialog_id, CandidateSource.USER_FEEDBACK
                )
            await session.commit()
            return feedback_dto(feedback), (
                await self._candidate_with_reviewer(session, candidate)
                if candidate
                else None
            )

    async def create_by_admin(
        self, admin: User, dialog_id: uuid.UUID
    ) -> KnowledgeCandidateDto:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError()
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id)
            if dialog is None:
                raise NotFoundError("Диалог не найден")
            if dialog.status != DialogStatus.CLOSED:
                raise ConflictError("Кандидат создаётся только из закрытого тикета")
            candidate = await self._create_or_get_candidate(
                session, dialog_id, CandidateSource.ADMIN
            )
            await session.commit()
            return await self._candidate_with_reviewer(session, candidate)

    async def get_candidate(
        self, admin: User, candidate_id: uuid.UUID
    ) -> KnowledgeCandidateDto:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError()
        async with self._session_factory() as session:
            candidate = await session.get(KnowledgeCandidate, candidate_id)
            if candidate is None:
                raise NotFoundError("Кандидат не найден")
            return await self._candidate_with_reviewer(session, candidate)

    async def patch_candidate(
        self, admin: User, candidate_id: uuid.UUID, card: CaseCard
    ) -> KnowledgeCandidateDto:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError()
        async with self._session_factory() as session:
            candidate = await session.get(
                KnowledgeCandidate, candidate_id, with_for_update=True
            )
            if candidate is None:
                raise NotFoundError("Кандидат не найден")
            if candidate.status != CandidateStatus.PENDING:
                raise ConflictError("Редактировать можно только pending-кандидата")
            candidate.generated_card = card.model_dump(mode="json")
            await session.commit()
            return await self._candidate_with_reviewer(session, candidate)

    async def approve(
        self,
        admin: User,
        candidate_id: uuid.UUID,
        section_id: uuid.UUID | None,
    ) -> KnowledgeCandidateDto:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError()
        async with self._lock_for(candidate_id):
            async with self._session_factory() as session:
                candidate = await session.get(
                    KnowledgeCandidate, candidate_id, with_for_update=True
                )
                if candidate is None:
                    raise NotFoundError("Кандидат не найден")
                if candidate.status == CandidateStatus.APPROVED:
                    return await self._candidate_with_reviewer(session, candidate)
                if candidate.status != CandidateStatus.PENDING:
                    raise ConflictError("Отклонённый кандидат нельзя опубликовать")
                target_section_id = section_id or DEFAULT_CASE_SECTION_ID
                section = await session.get(KnowledgeSection, target_section_id)
                if section is None:
                    raise NotFoundError("Целевой раздел базы знаний не найден")
                card = CaseCard.model_validate(candidate.generated_card)

            markdown = self._render_markdown(card)
            upload = ValidatedUpload(
                file_name=f"{candidate_id}.md",
                extension=".md",
                mime_type="text/markdown",
                data=markdown.encode("utf-8"),
            )
            document = await self._knowledge_base.create_document(
                upload=upload,
                section_id=target_section_id,
                source_type=DocumentSourceType.RESOLVED_CASE,
                title=card.title,
                one_c_version=None,
                tags=["resolved_case"],
                schedule_ingestion=False,
                storage_key=f"case-cards/{candidate_id}.md",
            )
            try:
                await self._knowledge_base.ingest(document.id)
            except IngestionFailedError as exc:
                try:
                    await self._knowledge_base.delete_document(document.id)
                except Exception:
                    logger.exception(
                        "Failed to compensate candidate document %s", document.id
                    )
                raise ConflictError(
                    "Кандидат не опубликован: индексация завершилась ошибкой"
                ) from exc

            async with self._session_factory() as session:
                candidate = await session.get(
                    KnowledgeCandidate, candidate_id, with_for_update=True
                )
                if candidate is None:
                    await self._knowledge_base.delete_document(document.id)
                    raise NotFoundError("Кандидат был удалён во время индексации")
                if candidate.status != CandidateStatus.PENDING:
                    await self._knowledge_base.delete_document(document.id)
                    raise ConflictError(
                        "Статус кандидата изменился во время индексации"
                    )
                candidate.status = CandidateStatus.APPROVED
                candidate.resulting_document_id = document.id
                candidate.reviewed_by = admin.id
                candidate.reviewed_at = datetime.now(UTC)
                await session.commit()
                return await self._candidate_with_reviewer(session, candidate)

    async def reject(
        self, admin: User, candidate_id: uuid.UUID
    ) -> KnowledgeCandidateDto:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError()
        async with self._session_factory() as session:
            candidate = await session.get(
                KnowledgeCandidate, candidate_id, with_for_update=True
            )
            if candidate is None:
                raise NotFoundError("Кандидат не найден")
            if candidate.status == CandidateStatus.REJECTED:
                return await self._candidate_with_reviewer(session, candidate)
            if candidate.status == CandidateStatus.APPROVED:
                raise ConflictError("Опубликованный кандидат нельзя отклонить")
            candidate.status = CandidateStatus.REJECTED
            candidate.reviewed_by = admin.id
            candidate.reviewed_at = datetime.now(UTC)
            await session.commit()
            return await self._candidate_with_reviewer(session, candidate)

    async def hard_delete_dialog(self, admin: User, dialog_id: uuid.UUID) -> None:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError()
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id)
            if dialog is None:
                raise NotFoundError("Диалог не найден")
            feedback = await session.scalar(
                select(DialogFeedback).where(DialogFeedback.dialog_id == dialog_id)
            )
            if (
                dialog.status != DialogStatus.CLOSED
                or feedback is None
                or feedback.verdict != FeedbackVerdict.AI_ERROR
            ):
                raise ConflictError(
                    "Удалять можно только закрытый тикет с оценкой ai_error"
                )
            candidate = await session.scalar(
                select(KnowledgeCandidate).where(
                    KnowledgeCandidate.dialog_id == dialog_id
                )
            )
            if candidate is not None and candidate.status == CandidateStatus.PENDING:
                raise ConflictError("Сначала отклоните кандидата в БЗ")
            if (
                candidate is not None
                and candidate.status == CandidateStatus.APPROVED
                and candidate.resulting_document_id is not None
            ):
                raise ConflictError(
                    "Диалог связан с опубликованным документом БЗ; "
                    "сначала удалите опубликованный материал"
                )
            attachments = list(
                await session.scalars(
                    select(Attachment)
                    .join(Message, Attachment.message_id == Message.id)
                    .where(Message.dialog_id == dialog_id)
                )
            )
            runtime = await self._settings_service.get_runtime(session)
        remote_ids = [
            item.gigachat_file_id
            for item in attachments
            if item.gigachat_file_id and item.remote_deleted_at is None
        ]
        if remote_ids:
            try:
                await self._attachment_service.cleanup_remote(
                    remote_ids, runtime.active_model, dialog_id
                )
            except ProviderError as exc:
                raise ServiceUnavailableError(str(exc)) from exc
        try:
            await self._attachment_service.cleanup_local(
                [item.storage_key for item in attachments]
            )
        except StorageError as exc:
            raise ServiceUnavailableError(
                "Не удалось очистить вложения диалога"
            ) from exc
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id, with_for_update=True)
            if dialog is not None:
                await session.delete(dialog)
                await session.commit()

    async def _create_or_get_candidate(
        self,
        session: AsyncSession,
        dialog_id: uuid.UUID,
        source: CandidateSource,
    ) -> KnowledgeCandidate:
        existing = await session.scalar(
            select(KnowledgeCandidate).where(KnowledgeCandidate.dialog_id == dialog_id)
        )
        if existing is not None:
            return existing
        card = await self._build_case_card(session, dialog_id)
        candidate = KnowledgeCandidate(
            dialog_id=dialog_id,
            source=source,
            generated_card=card.model_dump(mode="json"),
            status=CandidateStatus.PENDING,
        )
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
            return candidate
        except IntegrityError:
            existing = await session.scalar(
                select(KnowledgeCandidate).where(
                    KnowledgeCandidate.dialog_id == dialog_id
                )
            )
            if existing is None:
                raise
            return existing

    async def _build_case_card(
        self, session: AsyncSession, dialog_id: uuid.UUID
    ) -> CaseCard:
        messages = list(
            await session.scalars(
                select(Message)
                .where(Message.dialog_id == dialog_id)
                .order_by(Message.created_at, Message.id)
            )
        )
        user_messages = [
            message.text
            for message in messages
            if message.author_type == MessageAuthor.USER and message.text
        ]
        solutions = [
            message.text
            for message in messages
            if message.author_type in {MessageAuthor.ASSISTANT, MessageAuthor.OPERATOR}
            and message.text
        ]
        problem = user_messages[0] if user_messages else "Проблема описана во вложении"
        attachments = list(
            await session.scalars(
                select(Attachment)
                .join(Message, Attachment.message_id == Message.id)
                .where(Message.dialog_id == dialog_id)
            )
        )
        attachment_symptoms = [
            value
            for attachment in attachments
            for value in (attachment.extracted_text, attachment.visual_summary)
            if value
        ]
        feedback = await session.scalar(
            select(DialogFeedback).where(DialogFeedback.dialog_id == dialog_id)
        )
        if feedback is None:
            result = "Обращение закрыто без итоговой оценки пользователя."
        elif feedback.verdict == FeedbackVerdict.HELPFUL:
            result = "Пользователь подтвердил, что решение помогло."
        else:
            result = "Пользователь отметил ошибку AI; карточка требует проверки."
        context_lines = [
            f"{message.author_type.value}: {message.text}"
            for message in messages
            if message.text
        ]
        return CaseCard(
            title=problem[:120],
            problem=problem,
            symptoms="\n".join(attachment_symptoms or user_messages[:3]) or problem,
            context="\n".join(context_lines) or problem,
            solution="\n".join(solutions)
            or (
                "Решение в диалоге не зафиксировано; "
                "требуется редактура администратора."
            ),
            result=result,
        )

    async def _candidate_with_reviewer(
        self,
        session: AsyncSession,
        candidate: KnowledgeCandidate,
    ) -> KnowledgeCandidateDto:
        reviewer = (
            await session.get(User, candidate.reviewed_by)
            if candidate.reviewed_by
            else None
        )
        resulting_document = (
            await session.get(KnowledgeDocument, candidate.resulting_document_id)
            if candidate.resulting_document_id
            else None
        )
        resulting_section = (
            await session.get(KnowledgeSection, resulting_document.section_id)
            if resulting_document is not None
            else None
        )
        return candidate_dto(
            candidate,
            reviewer,
            resulting_document,
            resulting_section,
        )

    @staticmethod
    def _render_markdown(card: CaseCard) -> str:
        return (
            f"# {card.title}\n\n"
            f"## Проблема\n{card.problem}\n\n"
            f"## Симптомы / текст ошибки\n{card.symptoms}\n\n"
            f"## Контекст\n{card.context}\n\n"
            f"## Решение\n{card.solution}\n\n"
            f"## Результат\n{card.result}\n"
        )
