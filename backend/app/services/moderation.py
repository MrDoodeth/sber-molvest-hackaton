from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.mappers import candidate_dto, feedback_dto, normalize_case_card
from app.contracts.schemas import (
    CaseCard,
    FeedbackDto,
    KnowledgeCandidateDto,
)
from app.core.constants import CASE_CARD_UNKNOWN, DEFAULT_CASE_SECTION_ID
from app.core.enums import (
    CandidateSource,
    CandidateStatus,
    DialogMode,
    DialogStatus,
    DocumentSourceType,
    FeedbackVerdict,
    MessageAuthor,
    PromptType,
    UserRole,
)
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.generation_gate import GenerationGate
from app.models import (
    Attachment,
    Dialog,
    DialogFeedback,
    KnowledgeCandidate,
    KnowledgeDocument,
    KnowledgeSection,
    Message,
    MetricEvent,
    User,
)
from app.providers.interfaces import (
    LLMProvider,
    ProviderError,
    StorageError,
)
from app.services.attachments import AttachmentService, ValidatedUpload
from app.services.generation_context import GenerationContextService
from app.services.kb import IngestionFailedError, KnowledgeBaseService
from app.services.settings import PromptService, SettingsService

logger = logging.getLogger(__name__)


class ModerationService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        knowledge_base: KnowledgeBaseService,
        attachment_service: AttachmentService,
        settings_service: SettingsService,
        prompt_service: PromptService,
        generation_context: GenerationContextService,
        llm_provider: LLMProvider,
        generation_gate: GenerationGate,
    ) -> None:
        self._session_factory = session_factory
        self._knowledge_base = knowledge_base
        self._attachment_service = attachment_service
        self._settings_service = settings_service
        self._prompt_service = prompt_service
        self._generation_context = generation_context
        self._llm_provider = llm_provider
        self._generation_gate = generation_gate
        self._dialog_locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._candidate_locks: dict[uuid.UUID, asyncio.Lock] = {}

    def _dialog_lock_for(self, dialog_id: uuid.UUID) -> asyncio.Lock:
        return self._dialog_locks.setdefault(dialog_id, asyncio.Lock())

    def _lock_for(self, candidate_id: uuid.UUID) -> asyncio.Lock:
        return self._candidate_locks.setdefault(candidate_id, asyncio.Lock())

    async def add_feedback(
        self, user: User, dialog_id: uuid.UUID, verdict: FeedbackVerdict
    ) -> tuple[FeedbackDto, KnowledgeCandidateDto | None]:
        if user.role != UserRole.USER:
            raise ForbiddenError("Оценку оставляет только пользователь")
        async with self._dialog_lock_for(dialog_id):
            async with self._session_factory() as session:
                dialog = await session.get(Dialog, dialog_id, with_for_update=True)
                if dialog is None:
                    raise NotFoundError("Диалог не найден")
                if dialog.user_id != user.id:
                    raise ForbiddenError()
                if dialog.status != DialogStatus.CLOSED:
                    raise ConflictError("Оценка доступна только после закрытия тикета")
                feedback = await session.scalar(
                    select(DialogFeedback).where(DialogFeedback.dialog_id == dialog_id)
                )
                if feedback is not None:
                    if feedback.verdict != verdict:
                        raise ConflictError("Итоговая оценка уже сохранена")
                else:
                    feedback = DialogFeedback(dialog_id=dialog_id, verdict=verdict)
                    try:
                        async with session.begin_nested():
                            session.add(feedback)
                            await session.flush()
                    except IntegrityError as exc:
                        concurrent = await session.scalar(
                            select(DialogFeedback).where(
                                DialogFeedback.dialog_id == dialog_id
                            )
                        )
                        if concurrent is None:
                            raise ConflictError(
                                "Не удалось сохранить итоговую оценку"
                            ) from exc
                        if concurrent.verdict != verdict:
                            raise ConflictError(
                                "Итоговая оценка уже сохранена"
                            ) from exc
                        feedback = concurrent
                await session.commit()
                result = feedback_dto(feedback)

        candidate = await self.ensure_candidate_for_closed(dialog_id)
        return result, candidate

    async def ensure_candidate_for_closed(
        self, dialog_id: uuid.UUID
    ) -> KnowledgeCandidateDto:
        """Ensure every closed ticket has one moderation candidate."""
        async with self._dialog_lock_for(dialog_id):
            async with self._session_factory() as session:
                dialog = await session.get(Dialog, dialog_id, with_for_update=True)
                if dialog is None:
                    raise NotFoundError("Диалог не найден")
                if dialog.status != DialogStatus.CLOSED:
                    raise ConflictError("Кандидат создаётся только из закрытого тикета")
                candidate = await self.ensure_candidate_for_closed_session(
                    session, dialog_id
                )
                await session.commit()
                return await self._candidate_with_reviewer(session, candidate)

    async def recover_closed_candidates(self) -> None:
        """Backfill candidates for closed dialogs created before auto-candidates."""
        async with self._session_factory() as session:
            dialog_ids = list(
                await session.scalars(
                    select(Dialog.id).where(
                        Dialog.status == DialogStatus.CLOSED,
                        ~select(KnowledgeCandidate.id)
                        .where(KnowledgeCandidate.dialog_id == Dialog.id)
                        .exists(),
                    )
                )
            )
        for dialog_id in dialog_ids:
            await self.ensure_candidate_for_closed(dialog_id)

    async def ensure_candidate_for_closed_session(
        self, session: AsyncSession, dialog_id: uuid.UUID
    ) -> KnowledgeCandidate:
        """Create the initial candidate in an already locked dialog transaction."""
        candidate = await session.scalar(
            select(KnowledgeCandidate)
            .where(KnowledgeCandidate.dialog_id == dialog_id)
            .with_for_update()
        )
        if candidate is not None:
            return candidate

        dialog = await session.get(Dialog, dialog_id)
        if dialog is None:
            raise NotFoundError("Диалог не найден")
        if dialog.status != DialogStatus.CLOSED:
            raise ConflictError("Кандидат создаётся только из закрытого тикета")
        candidate = KnowledgeCandidate(
            dialog_id=dialog_id,
            source=(
                CandidateSource.OPERATOR
                if dialog.mode == DialogMode.OPERATOR_SUPPORT
                else CandidateSource.USER_FEEDBACK
            ),
            generated_card=(
                await self._initial_case_card(session, dialog_id)
            ).model_dump(mode="json"),
            status=CandidateStatus.PENDING,
        )
        session.add(candidate)
        await session.flush()
        return candidate

    async def _initial_case_card(
        self, session: AsyncSession, dialog_id: uuid.UUID
    ) -> CaseCard:
        messages = list(
            await session.scalars(
                select(Message)
                .where(Message.dialog_id == dialog_id)
                .order_by(Message.created_at, Message.id)
            )
        )
        first_user = next(
            (
                message
                for message in messages
                if message.author_type == MessageAuthor.USER
            ),
            None,
        )
        title = " ".join((first_user.text if first_user else "").split())
        title = title[:117].rstrip() + "..." if len(title) > 120 else title
        title = title or f"Обращение {str(dialog_id)[:8]}"
        return CaseCard(
            title=title,
            problem=CASE_CARD_UNKNOWN,
            result=CASE_CARD_UNKNOWN,
        )

    async def create_by_admin(
        self, admin: User, dialog_id: uuid.UUID
    ) -> KnowledgeCandidateDto:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError()
        async with self._dialog_lock_for(dialog_id):
            async with self._session_factory() as session:
                dialog = await session.get(Dialog, dialog_id, with_for_update=True)
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
        async with self._session_factory() as lookup_session:
            lookup = await lookup_session.get(KnowledgeCandidate, candidate_id)
            if lookup is None:
                raise NotFoundError("Кандидат не найден")
            dialog_id = lookup.dialog_id
        async with self._dialog_lock_for(dialog_id):
            async with self._lock_for(candidate_id):
                async with self._session_factory() as session:
                    candidate = await session.get(
                        KnowledgeCandidate, candidate_id, with_for_update=True
                    )
                    if candidate is None:
                        raise NotFoundError("Кандидат не найден")
                    if candidate.status != CandidateStatus.PENDING:
                        raise ConflictError(
                            "Редактировать можно только pending-кандидата"
                        )
                    candidate.generated_card = card.model_dump(mode="json")
                    await session.commit()
                    return await self._candidate_with_reviewer(session, candidate)

    async def approve(
        self,
        admin: User,
        candidate_id: uuid.UUID,
        card: CaseCard | None = None,
    ) -> KnowledgeCandidateDto:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError()
        async with self._session_factory() as lookup_session:
            lookup = await lookup_session.get(KnowledgeCandidate, candidate_id)
            if lookup is None:
                raise NotFoundError("Кандидат не найден")
            dialog_id = lookup.dialog_id
        async with self._dialog_lock_for(dialog_id):
            async with self._lock_for(candidate_id):
                async with self._session_factory() as session:
                    dialog = await session.get(Dialog, dialog_id, with_for_update=True)
                    if dialog is None:
                        raise NotFoundError("Диалог кандидата не найден")
                    candidate = await session.get(
                        KnowledgeCandidate, candidate_id, with_for_update=True
                    )
                    if candidate is None:
                        raise NotFoundError("Кандидат не найден")
                    if candidate.status == CandidateStatus.APPROVED:
                        return await self._candidate_with_reviewer(session, candidate)
                    if candidate.status != CandidateStatus.PENDING:
                        raise ConflictError("Отклонённый кандидат нельзя опубликовать")
                    target_section_id = DEFAULT_CASE_SECTION_ID
                    section = await session.get(KnowledgeSection, target_section_id)
                    if section is None:
                        raise NotFoundError("Целевой раздел базы знаний не найден")
                    if card is not None:
                        candidate.generated_card = card.model_dump(mode="json")
                    card = normalize_case_card(candidate.generated_card)
                    candidate.generated_card = card.model_dump(mode="json")

                    # Keep both row locks until publication is committed. A hard
                    # delete cannot remove the dialog while the document is built.
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
                                "Failed to compensate candidate document %s",
                                document.id,
                            )
                        raise ConflictError(
                            "Кандидат не опубликован: индексация завершилась ошибкой"
                        ) from exc

                    candidate.status = CandidateStatus.APPROVED
                    candidate.resulting_document_id = document.id
                    candidate.reviewed_by = admin.id
                    candidate.reviewed_at = datetime.now(UTC)
                    try:
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        try:
                            await self._knowledge_base.delete_document(document.id)
                        except Exception:
                            logger.exception(
                                "Failed to compensate published candidate document %s",
                                document.id,
                            )
                        raise
                    return await self._candidate_with_reviewer(session, candidate)

    async def generate_card(
        self, admin: User, candidate_id: uuid.UUID
    ) -> KnowledgeCandidateDto:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError()
        async with self._session_factory() as lookup_session:
            lookup = await lookup_session.get(KnowledgeCandidate, candidate_id)
            if lookup is None:
                raise NotFoundError("Кандидат не найден")
            dialog_id = lookup.dialog_id
        async with self._dialog_lock_for(dialog_id):
            async with self._lock_for(candidate_id):
                async with self._session_factory() as session:
                    candidate = await session.get(
                        KnowledgeCandidate, candidate_id, with_for_update=True
                    )
                    if candidate is None:
                        raise NotFoundError("Кандидат не найден")
                    if candidate.status != CandidateStatus.PENDING:
                        raise ConflictError(
                            "Заполнить карточку можно только для pending-кандидата"
                        )
                    card = await self._build_case_card(session, dialog_id)
                    candidate.generated_card = card.model_dump(mode="json")
                    await session.commit()
                    return await self._candidate_with_reviewer(session, candidate)

    async def reject(
        self, admin: User, candidate_id: uuid.UUID
    ) -> KnowledgeCandidateDto:
        if admin.role != UserRole.ADMIN:
            raise ForbiddenError()
        async with self._session_factory() as lookup_session:
            lookup = await lookup_session.get(KnowledgeCandidate, candidate_id)
            if lookup is None:
                raise NotFoundError("Кандидат не найден")
            dialog_id = lookup.dialog_id
        async with self._dialog_lock_for(dialog_id):
            async with self._lock_for(candidate_id):
                async with self._session_factory() as session:
                    dialog = await session.get(Dialog, dialog_id, with_for_update=True)
                    if dialog is None:
                        raise NotFoundError("Диалог кандидата не найден")
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
        async with self._dialog_lock_for(dialog_id):
            async with self._session_factory() as session:
                # Keep the dialog and candidate locks until all cleanup and the
                # hard delete commit. Approve uses the same lock order.
                dialog = await session.get(Dialog, dialog_id, with_for_update=True)
                if dialog is None:
                    raise NotFoundError("Диалог не найден")
                if dialog.status != DialogStatus.CLOSED:
                    raise ConflictError("Удалять можно только закрытый тикет")
                candidate = await session.scalar(
                    select(KnowledgeCandidate)
                    .where(KnowledgeCandidate.dialog_id == dialog_id)
                    .with_for_update()
                )
                if (
                    candidate is not None
                    and candidate.status == CandidateStatus.PENDING
                ):
                    raise ConflictError("Сначала отклоните кандидата в БЗ")
                if (
                    candidate is not None
                    and candidate.status == CandidateStatus.APPROVED
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
                        async with self._generation_gate.acquire():
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
        feedback = await session.scalar(
            select(DialogFeedback).where(DialogFeedback.dialog_id == dialog_id)
        )
        runtime = await self._settings_service.get_runtime(session)
        prompt = await self._prompt_service.get_active(
            session, PromptType.KNOWLEDGE_CARD
        )
        feedback_context = (
            "Итоговая оценка пользователя: оценка ещё не сохранена."
            if feedback is None
            else (
                "Итоговая оценка пользователя: решение помогло."
                if feedback.verdict == FeedbackVerdict.HELPFUL
                else "Итоговая оценка пользователя: AI допустил ошибку."
            )
        )
        started = time.monotonic()
        context: Any | None = None
        success = False
        error_message: str | None = None
        try:
            async with self._generation_gate.acquire():
                try:
                    context = await self._generation_context.build_for_knowledge_card(
                        dialog_id=dialog_id,
                        system_prompt=prompt.content,
                        settings=runtime,
                        instruction=(
                            "Сформируй поля карточки решённого случая для последующей "
                            "проверки администратором. "
                            f"{feedback_context}"
                        ),
                    )
                    card = await self._llm_provider.generate_case_card(
                        context.request,
                        runtime.active_model,
                        runtime.gigachat_max_output_tokens,
                        dialog_id,
                    )
                    success = True
                    return card
                except ProviderError as exc:
                    error_message = str(exc)
                    raise ServiceUnavailableError(str(exc)) from exc
                finally:
                    if context is not None:
                        await self._cleanup_generation_attachments(
                            dialog_id,
                            list(context.request.attachment_file_ids),
                            runtime.active_model,
                        )
        except Exception as exc:
            if error_message is None:
                error_message = str(exc)
            raise
        finally:
            await self._record_metric(
                dialog_id=dialog_id,
                started=started,
                runtime=runtime,
                prompt_content=prompt.content,
                event_type="knowledge_card",
                success=success,
                error_message=error_message,
            )

    async def _cleanup_generation_attachments(
        self, dialog_id: uuid.UUID, file_ids: list[str], model: str
    ) -> None:
        if not file_ids:
            return
        try:
            await self._attachment_service.cleanup_remote(file_ids, model, dialog_id)
        except ProviderError:
            logger.exception(
                "Unable to remove knowledge-card files for dialog %s", dialog_id
            )
            return
        deleted_at = datetime.now(UTC)
        async with self._session_factory() as session:
            attachments = list(
                await session.scalars(
                    select(Attachment)
                    .join(Message, Attachment.message_id == Message.id)
                    .where(
                        Message.dialog_id == dialog_id,
                        Attachment.gigachat_file_id.in_(file_ids),
                    )
                )
            )
            for attachment in attachments:
                attachment.remote_deleted_at = deleted_at
            await session.commit()

    async def _record_metric(
        self,
        *,
        dialog_id: uuid.UUID,
        started: float,
        runtime: Any,
        prompt_content: str,
        event_type: str,
        success: bool,
        error_message: str | None,
    ) -> None:
        try:
            async with self._session_factory() as session:
                session.add(
                    MetricEvent(
                        dialog_id=dialog_id,
                        event_type=event_type,
                        success=success,
                        error_message=error_message[:4000] if error_message else None,
                        latency_ms=max(0, round((time.monotonic() - started) * 1000)),
                        gigachat_model=runtime.active_model,
                        system_prompt=prompt_content,
                        rag_top_k=runtime.rag_top_k,
                        operator_escalation_threshold=(
                            runtime.operator_escalation_threshold
                        ),
                    )
                )
                await session.commit()
        except Exception:
            logger.exception(
                "Unable to persist %s metric for dialog %s", event_type, dialog_id
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
            f"## Результат\n{card.result}\n"
        )
