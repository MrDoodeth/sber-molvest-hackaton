from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.mappers import (
    dialog_detail,
    dialog_summary,
    draft_dto,
    message_dto,
)
from app.contracts.schemas import (
    DialogDetail,
    DialogSummary,
    MessageDto,
    MessagePage,
    OperatorDraftDto,
)
from app.core.constants import (
    CLOSED_SYSTEM_MESSAGE,
    ESCALATION_SYSTEM_MESSAGE,
)
from app.core.enums import (
    DialogChannel,
    DialogMode,
    DialogStatus,
    MessageAuthor,
    MessageProcessingStatus,
    PromptType,
    UserRole,
)
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableError,
)
from app.models import (
    Attachment,
    Dialog,
    DialogFeedback,
    KnowledgeCandidate,
    Message,
    MetricEvent,
    OperatorDraft,
    User,
)
from app.providers.interfaces import (
    ChatTurn,
    HybridEmbedding,
    LLMProvider,
    ProviderError,
    ProviderPolicyError,
    ProviderServerError,
    ProviderUsage,
    StorageError,
)
from app.services.attachments import (
    RUNTIME_IMAGE_MIME_TYPES,
    AttachmentService,
    ValidatedUpload,
)
from app.services.broker import (
    OPERATOR_QUEUE_CHANNEL,
    EventBroker,
    operator_dialog_channel,
    user_dialog_channel,
)
from app.services.context import ContextBuilder
from app.services.model_output import ModelOutputStreamFilter
from app.services.rag import RAGService
from app.services.settings import PromptService, RuntimeSettings, SettingsService
from app.services.tasks import TaskSupervisor

logger = logging.getLogger(__name__)


class DialogService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        attachment_service: AttachmentService,
        settings_service: SettingsService,
        prompt_service: PromptService,
        context_builder: ContextBuilder,
        rag_service: RAGService,
        llm_provider: LLMProvider,
        broker: EventBroker,
        tasks: TaskSupervisor,
    ) -> None:
        self._session_factory = session_factory
        self._attachment_service = attachment_service
        self._settings_service = settings_service
        self._prompt_service = prompt_service
        self._context_builder = context_builder
        self._rag_service = rag_service
        self._llm_provider = llm_provider
        self._broker = broker
        self._tasks = tasks
        self._dialog_locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._processing_message_ids: set[uuid.UUID] = set()
        self._pending_ai_dialogs: set[uuid.UUID] = set()
        self._gigachat_semaphore = asyncio.Semaphore(1)

    def dialog_lock(self, dialog_id: uuid.UUID) -> asyncio.Lock:
        return self._dialog_locks.setdefault(dialog_id, asyncio.Lock())

    def _schedule_processing(
        self,
        message_id: uuid.UUID,
        dialog_id: uuid.UUID,
        mode: DialogMode,
    ) -> None:
        if message_id in self._processing_message_ids:
            return
        self._processing_message_ids.add(message_id)
        if mode == DialogMode.AI_SUPPORT:
            self._pending_ai_dialogs.add(dialog_id)

        async def run() -> None:
            try:
                await self.process_user_message(message_id)
            finally:
                self._processing_message_ids.discard(message_id)
                if mode == DialogMode.AI_SUPPORT:
                    self._pending_ai_dialogs.discard(dialog_id)

        self._tasks.spawn(run())

    async def recover_pending_turns(self) -> None:
        async with self._session_factory() as session:
            dialogs = list(
                await session.scalars(
                    select(Dialog).where(Dialog.status == DialogStatus.ACTIVE)
                )
            )
            pending: list[tuple[uuid.UUID, uuid.UUID, DialogMode]] = []
            for dialog in dialogs:
                triggers = list(
                    await session.scalars(
                        select(Message)
                        .where(
                            Message.dialog_id == dialog.id,
                            Message.author_type == MessageAuthor.USER,
                        )
                        .order_by(Message.created_at, Message.id)
                    )
                )
                for trigger in triggers:
                    if not await self._turn_completed(session, trigger, dialog):
                        pending.append((trigger.id, dialog.id, dialog.mode))
        for message_id, dialog_id, mode in pending:
            self._schedule_processing(message_id, dialog_id, mode)

    async def create_dialog(self, user: User) -> DialogDetail:
        if user.role != UserRole.USER:
            raise ForbiddenError("Создавать обращения может только пользователь")
        async with self._session_factory() as session:
            dialog = Dialog(
                user_id=user.id,
                status=DialogStatus.ACTIVE,
                mode=DialogMode.AI_SUPPORT,
                channel=DialogChannel.WEB,
                dialog_confidence=1.0,
            )
            session.add(dialog)
            await session.commit()
            persisted_user = await session.get(User, user.id)
            if persisted_user is None:
                raise NotFoundError("Пользователь не найден")
            return dialog_detail(dialog, persisted_user)

    async def list_user_dialogs(self, user: User) -> list[DialogSummary]:
        if user.role != UserRole.USER:
            raise ForbiddenError("Endpoint доступен только пользователю")
        async with self._session_factory() as session:
            dialogs = (
                await session.scalars(
                    select(Dialog)
                    .where(
                        Dialog.user_id == user.id,
                        Dialog.id.in_(
                            select(Message.dialog_id).where(
                                Message.author_type == MessageAuthor.USER
                            )
                        ),
                    )
                    .order_by(Dialog.updated_at.desc())
                )
            ).all()
            return [await self._summary(session, dialog) for dialog in dialogs]

    async def get_dialog(self, requester: User, dialog_id: uuid.UUID) -> DialogDetail:
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id)
            if dialog is None:
                raise NotFoundError("Диалог не найден")
            self._assert_read_access(requester, dialog)
            return await self._detail(session, requester, dialog)

    async def list_messages(
        self,
        requester: User,
        dialog_id: uuid.UUID,
        cursor: uuid.UUID | None,
        limit: int,
    ) -> MessagePage:
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id)
            if dialog is None:
                raise NotFoundError("Диалог не найден")
            self._assert_read_access(requester, dialog)
            statement = select(Message).where(Message.dialog_id == dialog_id)
            if cursor is not None:
                cursor_message = await session.get(Message, cursor)
                if cursor_message is None or cursor_message.dialog_id != dialog_id:
                    raise UnprocessableError("Некорректный cursor")
                statement = statement.where(
                    or_(
                        Message.created_at < cursor_message.created_at,
                        and_(
                            Message.created_at == cursor_message.created_at,
                            Message.id < cursor_message.id,
                        ),
                    )
                )
            fetched = list(
                await session.scalars(
                    statement.order_by(
                        Message.created_at.desc(), Message.id.desc()
                    ).limit(limit + 1)
                )
            )
            has_more = len(fetched) > limit
            selected = fetched[:limit]
            next_cursor = selected[-1].id if has_more and selected else None
            selected.reverse()
            attachments = await self._attachments_by_message(
                session, [message.id for message in selected]
            )
            return MessagePage(
                items=[
                    message_dto(message, attachments.get(message.id, []))
                    for message in selected
                ],
                next_cursor=next_cursor,
            )

    async def persist_message(
        self,
        *,
        requester: User,
        dialog_id: uuid.UUID,
        client_message_id: uuid.UUID,
        text: str,
        uploads: list[ValidatedUpload],
        defer_processing: bool = False,
    ) -> tuple[MessageDto, bool]:
        async with self.dialog_lock(dialog_id):
            return await self._persist_message_locked(
                requester=requester,
                dialog_id=dialog_id,
                client_message_id=client_message_id,
                text=text,
                uploads=uploads,
                defer_processing=defer_processing,
            )

    async def _persist_message_locked(
        self,
        *,
        requester: User,
        dialog_id: uuid.UUID,
        client_message_id: uuid.UUID,
        text: str,
        uploads: list[ValidatedUpload],
        defer_processing: bool,
    ) -> tuple[MessageDto, bool]:
        normalized_text = text.strip()
        if not normalized_text and not uploads:
            raise UnprocessableError("Сообщение или вложение обязательно")
        if len(normalized_text) > 20_000:
            raise UnprocessableError("Текст сообщения слишком длинный")
        if requester.role not in {UserRole.USER, UserRole.OPERATOR}:
            raise ForbiddenError("Эта роль не может отправлять сообщения")

        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id)
            if dialog is None:
                raise NotFoundError("Диалог не найден")
            existing = await session.scalar(
                select(Message).where(
                    Message.dialog_id == dialog_id,
                    Message.client_message_id == client_message_id,
                )
            )
            if existing is not None:
                self._assert_read_access(requester, dialog)
                expected_author = (
                    MessageAuthor.USER
                    if requester.role == UserRole.USER
                    else MessageAuthor.OPERATOR
                )
                if existing.author_type != expected_author:
                    raise ConflictError(
                        "client_message_id уже использован другим автором"
                    )
                existing_attachments = await self._attachments_by_message(
                    session, [existing.id]
                )
                if (
                    dialog.status == DialogStatus.ACTIVE
                    and existing.author_type == MessageAuthor.USER
                ):
                    if existing.processing_status == MessageProcessingStatus.FAILED:
                        existing.processing_status = MessageProcessingStatus.PENDING
                        existing.processing_error = None
                        await session.commit()
                    if not defer_processing:
                        self._schedule_processing(existing.id, dialog_id, dialog.mode)
                return message_dto(
                    existing, existing_attachments.get(existing.id, [])
                ), False

            self._assert_send_access(requester, dialog)

            if (
                requester.role == UserRole.USER
                and dialog.mode == DialogMode.AI_SUPPORT
                and dialog_id in self._pending_ai_dialogs
            ):
                raise ConflictError("Дождитесь завершения текущего ответа AI")

            message = Message(
                id=uuid.uuid4(),
                dialog_id=dialog_id,
                client_message_id=client_message_id,
                author_type=(
                    MessageAuthor.USER
                    if requester.role == UserRole.USER
                    else MessageAuthor.OPERATOR
                ),
                text=normalized_text,
                sources=[],
                processing_status=(
                    MessageProcessingStatus.PENDING
                    if requester.role == UserRole.USER
                    else None
                ),
            )
            session.add(message)
            try:
                await session.flush()
            except IntegrityError as exc:
                await session.rollback()
                existing = await session.scalar(
                    select(Message).where(
                        Message.dialog_id == dialog_id,
                        Message.client_message_id == client_message_id,
                    )
                )
                if existing is None:
                    raise ConflictError("Не удалось сохранить сообщение") from exc
                expected_author = (
                    MessageAuthor.USER
                    if requester.role == UserRole.USER
                    else MessageAuthor.OPERATOR
                )
                if existing.author_type != expected_author:
                    raise ConflictError(
                        "client_message_id уже использован другим автором"
                    ) from exc
                existing_attachments = await self._attachments_by_message(
                    session, [existing.id]
                )
                return message_dto(
                    existing, existing_attachments.get(existing.id, [])
                ), False

            stored_keys: list[str] = []
            attachments: list[Attachment] = []
            try:
                for upload in uploads:
                    storage_key = await self._attachment_service.store_runtime(
                        message.id, upload
                    )
                    attachments.append(
                        Attachment(
                            message_id=message.id,
                            storage_key=storage_key,
                            mime_type=upload.mime_type,
                            size_bytes=len(upload.data),
                        )
                    )
                    stored_keys.append(storage_key)
                session.add_all(attachments)
                dialog.updated_at = datetime.now(UTC)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                if stored_keys:
                    await self._attachment_service.cleanup_local(stored_keys)
                if isinstance(exc, StorageError):
                    raise ServiceUnavailableError(
                        "Хранилище вложений временно недоступно"
                    ) from exc
                raise
            dto = message_dto(message, attachments)
            mode = dialog.mode

        payload = dto.model_dump(mode="json")
        if requester.role == UserRole.USER:
            if mode == DialogMode.OPERATOR_SUPPORT:
                await self._broker.publish(
                    operator_dialog_channel(dialog_id),
                    {"type": "user_message", "message": payload},
                )
            if not defer_processing:
                self._schedule_processing(message.id, dialog_id, mode)
        else:
            await self._broker.publish(
                user_dialog_channel(dialog_id),
                {"type": "operator_message", "message": payload},
            )
        return dto, True

    async def schedule_processing(self, message_id: uuid.UUID) -> None:
        """Schedule a persisted user turn after its HTTP response is sent."""
        async with self._session_factory() as session:
            message = await session.get(Message, message_id)
            if message is None or message.author_type != MessageAuthor.USER:
                return
            dialog = await session.get(Dialog, message.dialog_id)
            if dialog is None or dialog.status != DialogStatus.ACTIVE:
                return
            if await self._turn_completed(session, message, dialog):
                return
            mode = dialog.mode
        self._schedule_processing(message_id, message.dialog_id, mode)

    async def operator_queue(self, operator: User, scope: str) -> list[DialogSummary]:
        if operator.role != UserRole.OPERATOR:
            raise ForbiddenError("Endpoint доступен только оператору")
        if scope not in {"unassigned", "mine"}:
            raise UnprocessableError("scope должен быть unassigned или mine")
        async with self._session_factory() as session:
            statement = select(Dialog).where(
                Dialog.status == DialogStatus.ACTIVE,
                Dialog.mode == DialogMode.OPERATOR_SUPPORT,
            )
            if scope == "unassigned":
                statement = statement.where(Dialog.assigned_operator_id.is_(None))
            else:
                statement = statement.where(Dialog.assigned_operator_id == operator.id)
            dialogs = list(
                await session.scalars(statement.order_by(Dialog.escalated_at.asc()))
            )
            return [await self._summary(session, dialog) for dialog in dialogs]

    async def latest_operator_draft(
        self, operator: User, dialog_id: uuid.UUID
    ) -> OperatorDraftDto | None:
        if operator.role != UserRole.OPERATOR:
            raise ForbiddenError("Endpoint доступен только оператору")
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id)
            if dialog is None:
                raise NotFoundError("Диалог не найден")
            self._assert_read_access(operator, dialog)
            draft = await session.scalar(
                select(OperatorDraft)
                .where(OperatorDraft.dialog_id == dialog_id)
                .order_by(OperatorDraft.created_at.desc(), OperatorDraft.id.desc())
                .limit(1)
            )
            return draft_dto(draft) if draft is not None else None

    async def claim(self, operator: User, dialog_id: uuid.UUID) -> DialogDetail:
        if operator.role != UserRole.OPERATOR:
            raise ForbiddenError("Endpoint доступен только оператору")
        async with self._session_factory() as session:
            result = await session.execute(
                update(Dialog)
                .where(
                    Dialog.id == dialog_id,
                    Dialog.status == DialogStatus.ACTIVE,
                    Dialog.mode == DialogMode.OPERATOR_SUPPORT,
                    Dialog.assigned_operator_id.is_(None),
                )
                .values(
                    assigned_operator_id=operator.id,
                    updated_at=datetime.now(UTC),
                )
            )
            if result.rowcount != 1:
                await session.rollback()
                dialog = await session.get(Dialog, dialog_id)
                if dialog is None:
                    raise NotFoundError("Диалог не найден")
                if (
                    dialog.status != DialogStatus.ACTIVE
                    or dialog.mode != DialogMode.OPERATOR_SUPPORT
                ):
                    raise ConflictError("Тикет недоступен для назначения")
                raise ConflictError("Тикет уже взят другим оператором")
            await session.commit()
        detail = await self.get_dialog(operator, dialog_id)
        await self._broker.publish(
            OPERATOR_QUEUE_CHANNEL,
            {
                "type": "ticket_claimed",
                "dialogId": str(dialog_id),
                "operator": {
                    "id": str(operator.id),
                    "displayName": operator.display_name,
                },
            },
        )
        return detail

    async def close(self, requester: User, dialog_id: uuid.UUID) -> DialogDetail:
        async with self.dialog_lock(dialog_id):
            async with self._session_factory() as session:
                dialog = await session.get(Dialog, dialog_id)
                if dialog is None:
                    raise NotFoundError("Диалог не найден")
                if dialog.status == DialogStatus.CLOSED:
                    return await self.get_dialog(requester, dialog_id)
                if requester.role == UserRole.USER:
                    if dialog.user_id != requester.id:
                        raise ForbiddenError()
                    if dialog.mode != DialogMode.AI_SUPPORT:
                        raise ForbiddenError(
                            "Тикет с подключённым специалистом закрывает оператор"
                        )
                    latest_conversation_message = await session.scalar(
                        select(Message)
                        .where(
                            Message.dialog_id == dialog_id,
                            Message.author_type != MessageAuthor.SYSTEM,
                        )
                        .order_by(Message.created_at.desc(), Message.id.desc())
                        .limit(1)
                    )
                    if (
                        latest_conversation_message is None
                        or latest_conversation_message.author_type
                        != MessageAuthor.ASSISTANT
                    ):
                        raise ConflictError(
                            "Нельзя закрыть тикет до ответа AI на последнее сообщение"
                        )
                elif requester.role == UserRole.OPERATOR:
                    if (
                        dialog.mode != DialogMode.OPERATOR_SUPPORT
                        or dialog.assigned_operator_id != requester.id
                    ):
                        raise ForbiddenError("Закрыть тикет может назначенный оператор")
                else:
                    raise ForbiddenError("Эта роль не закрывает тикеты через chat API")

                settings = await self._settings_service.get_runtime(session)
                remote_attachments = list(
                    await session.scalars(
                        select(Attachment)
                        .join(Message, Attachment.message_id == Message.id)
                        .where(
                            Message.dialog_id == dialog_id,
                            Attachment.gigachat_file_id.is_not(None),
                            Attachment.remote_deleted_at.is_(None),
                        )
                    )
                )
                remote_ids = [
                    item.gigachat_file_id
                    for item in remote_attachments
                    if item.gigachat_file_id
                ]
            if remote_ids:
                try:
                    await self._attachment_service.cleanup_remote(
                        remote_ids, settings.active_model, dialog_id
                    )
                except ProviderError as exc:
                    raise ServiceUnavailableError(str(exc)) from exc

            closed_at = datetime.now(UTC)
            async with self._session_factory() as session:
                dialog = await session.get(Dialog, dialog_id, with_for_update=True)
                if dialog is None:
                    raise NotFoundError("Диалог не найден")
                if dialog.status == DialogStatus.ACTIVE:
                    dialog.status = DialogStatus.CLOSED
                    dialog.closed_at = closed_at
                    dialog.updated_at = closed_at
                    session.add(
                        Message(
                            dialog_id=dialog_id,
                            author_type=MessageAuthor.SYSTEM,
                            text=CLOSED_SYSTEM_MESSAGE,
                            sources=[],
                        )
                    )
                if remote_ids:
                    attachments = list(
                        await session.scalars(
                            select(Attachment)
                            .join(Message, Attachment.message_id == Message.id)
                            .where(
                                Message.dialog_id == dialog_id,
                                Attachment.gigachat_file_id.in_(remote_ids),
                            )
                        )
                    )
                    for attachment in attachments:
                        attachment.remote_deleted_at = closed_at
                mode = dialog.mode
                await session.commit()

            await self._broker.publish(
                user_dialog_channel(dialog_id), {"type": "dialog_closed"}
            )
            if mode == DialogMode.OPERATOR_SUPPORT:
                await self._broker.publish(
                    operator_dialog_channel(dialog_id), {"type": "dialog_closed"}
                )
                await self._broker.publish(
                    OPERATOR_QUEUE_CHANNEL,
                    {"type": "ticket_closed", "dialogId": str(dialog_id)},
                )
            return await self.get_dialog(requester, dialog_id)

    async def process_user_message(self, message_id: uuid.UUID) -> None:
        started = time.monotonic()
        dialog_id: uuid.UUID | None = None
        mode = DialogMode.AI_SUPPORT
        confidence: float | None = None
        source_snapshot: list[dict[str, object]] = []
        runtime_settings: RuntimeSettings | None = None
        prompt_version: int | None = None
        prompt_embedding_task: asyncio.Task[HybridEmbedding] | None = None
        try:
            async with self._session_factory() as session:
                trigger = await session.get(Message, message_id)
                if trigger is None or trigger.author_type != MessageAuthor.USER:
                    return
                dialog_id = trigger.dialog_id

            async with self.dialog_lock(dialog_id):
                async with self._session_factory() as session:
                    trigger = await session.get(Message, message_id)
                    dialog = await session.get(Dialog, dialog_id)
                    if (
                        trigger is None
                        or dialog is None
                        or dialog.status != DialogStatus.ACTIVE
                    ):
                        return
                    mode = dialog.mode
                    if await self._turn_completed(session, trigger, dialog):
                        return
                    trigger.processing_status = MessageProcessingStatus.PROCESSING
                    trigger.processing_error = None
                    dialog.updated_at = datetime.now(UTC)
                    await session.commit()
                    runtime_settings = await self._settings_service.get_runtime(session)
                    prompt_type = (
                        PromptType.USER_SUPPORT
                        if mode == DialogMode.AI_SUPPORT
                        else PromptType.OPERATOR_GIGACHAT
                    )
                    prompt = await self._prompt_service.get_active(session, prompt_type)
                    prompt_version = prompt.version
                    messages = list(
                        await session.scalars(
                            select(Message)
                            .where(Message.dialog_id == dialog_id)
                            .order_by(Message.created_at, Message.id)
                        )
                    )
                    trigger_index = next(
                        index
                        for index, item in enumerate(messages)
                        if item.id == message_id
                    )
                    previous = messages[:trigger_index]
                    all_attachments = await self._attachments_by_message(
                        session, [item.id for item in previous] + [message_id]
                    )
                    trigger_attachments = all_attachments.get(message_id, [])
                    history = self._history(previous, all_attachments)

                prompt_search_context = (
                    self._context_builder.build_prompt_embedding_context(
                        current_text=trigger.text,
                        history=history,
                        settings=runtime_settings,
                    )
                )
                prompt_embedding_task = asyncio.create_task(
                    self._rag_service.embed_query(prompt_search_context)
                )

                async with self._gigachat_semaphore:
                    attachment_file_ids: list[str] = []
                    attachment_mime_types: list[str] = []
                    for attachment in trigger_attachments:
                        if attachment.gigachat_file_id is None:
                            content = await self._attachment_service.storage.get(
                                attachment.storage_key
                            )
                            file_id = await self._llm_provider.upload_file(
                                PurePosixPath(attachment.storage_key).name,
                                content,
                                runtime_settings.active_model,
                                dialog_id,
                            )
                            async with self._session_factory() as session:
                                persisted = await session.get(Attachment, attachment.id)
                                if persisted is None:
                                    await self._llm_provider.delete_file(
                                        file_id,
                                        runtime_settings.active_model,
                                        dialog_id,
                                    )
                                    return
                                persisted.gigachat_file_id = file_id
                                await session.commit()
                            attachment.gigachat_file_id = file_id
                        if attachment.gigachat_file_id is not None:
                            attachment_file_ids.append(attachment.gigachat_file_id)
                            attachment_mime_types.append(attachment.mime_type)

                    vision_attachment = next(
                        (
                            item
                            for item in trigger_attachments
                            if item.mime_type in RUNTIME_IMAGE_MIME_TYPES
                        ),
                        None,
                    )
                    if vision_attachment is not None and (
                        vision_attachment.extracted_text is None
                        or vision_attachment.visual_summary is None
                    ):
                        if vision_attachment.gigachat_file_id is None:
                            raise ProviderServerError("GigaChat file_id не сохранён")
                        analysis = await self._llm_provider.analyze_screenshot(
                            vision_attachment.gigachat_file_id,
                            trigger.text,
                            runtime_settings.active_model,
                            dialog_id,
                        )
                        async with self._session_factory() as session:
                            persisted = await session.get(
                                Attachment, vision_attachment.id
                            )
                            if persisted is not None:
                                persisted.extracted_text = analysis.extracted_text
                                persisted.visual_summary = analysis.visual_summary
                                await session.commit()
                        vision_attachment.extracted_text = analysis.extracted_text
                        vision_attachment.visual_summary = analysis.visual_summary

                    if prompt_embedding_task is None:
                        raise ProviderServerError(
                            "Не удалось подготовить embedding запроса"
                        )
                    query_embeddings = [await prompt_embedding_task]
                    if vision_attachment is not None:
                        screenshot_search_context = (
                            self._context_builder.build_screenshot_embedding_context(
                                extracted_text=vision_attachment.extracted_text,
                                visual_summary=vision_attachment.visual_summary,
                                settings=runtime_settings,
                            )
                        )
                        query_embeddings.append(
                            await self._rag_service.embed_query(
                                screenshot_search_context
                            )
                        )
                    async with self._session_factory() as session:
                        retrieval = await self._rag_service.retrieve_embeddings(
                            session,
                            query_embeddings,
                            runtime_settings.rag_top_k,
                            weights=[1.0] * len(query_embeddings),
                        )
                    evidence = retrieval.evidence
                    logger.info(
                        "RAG retrieval status=%s evidence_count=%d dialog=%s",
                        retrieval.status,
                        len(evidence),
                        dialog_id,
                    )
                    generation_request = self._context_builder.build_generation_request(
                        system_prompt=prompt.content,
                        current_text=trigger.text,
                        history=history,
                        evidence=evidence,
                        attachment_file_ids=attachment_file_ids,
                        attachment_mime_types=attachment_mime_types,
                        screenshot_extracted_text=(
                            vision_attachment.extracted_text
                            if vision_attachment
                            else None
                        ),
                        screenshot_visual_summary=(
                            vision_attachment.visual_summary
                            if vision_attachment
                            else None
                        ),
                        settings=runtime_settings,
                        rag_status=retrieval.status,
                    )
                    source_snapshot = [
                        item.source.model_dump(mode="json")
                        for item in generation_request.evidence
                    ]
                    assessment = await self._llm_provider.assess_confidence(
                        generation_request,
                        runtime_settings.active_model,
                        dialog_id,
                    )
                    confidence = assessment.confidence
                    await self._persist_confidence(
                        dialog_id, message_id, confidence, source_snapshot
                    )
                    if mode == DialogMode.AI_SUPPORT:
                        await self._broker.publish(
                            user_dialog_channel(dialog_id),
                            {"type": "confidence", "value": confidence},
                        )
                        if confidence < runtime_settings.operator_escalation_threshold:
                            await self._escalate(
                                dialog_id,
                                confidence,
                                source_snapshot,
                                started,
                                runtime_settings,
                                prompt_version,
                                message_id,
                            )
                            return
                    else:
                        await self._broker.publish(
                            operator_dialog_channel(dialog_id),
                            {
                                "type": "confidence",
                                "value": confidence,
                                "triggerMessageId": str(message_id),
                            },
                        )

                    output_filter = ModelOutputStreamFilter()
                    usage: ProviderUsage | None = None
                    async for chunk in self._llm_provider.stream_text(
                        generation_request,
                        runtime_settings.active_model,
                        runtime_settings.gigachat_max_output_tokens,
                        dialog_id,
                    ):
                        if chunk.usage is not None:
                            usage = chunk.usage
                        if not chunk.text:
                            continue
                        visible_text = output_filter.push(chunk.text)
                        if not visible_text:
                            continue
                        if mode == DialogMode.AI_SUPPORT:
                            await self._broker.publish(
                                user_dialog_channel(dialog_id),
                                {"type": "assistant_token", "token": visible_text},
                            )
                        else:
                            await self._broker.publish(
                                operator_dialog_channel(dialog_id),
                                {
                                    "type": "draft_token",
                                    "token": visible_text,
                                    "triggerMessageId": str(message_id),
                                },
                            )
                    generated_text = output_filter.final()
                    if not generated_text:
                        raise ProviderServerError("GigaChat вернул пустой ответ")

                if mode == DialogMode.AI_SUPPORT:
                    dto = await self._persist_assistant(
                        dialog_id,
                        generated_text,
                        confidence,
                        source_snapshot,
                        trigger_message_id=message_id,
                    )
                    await self._broker.publish(
                        user_dialog_channel(dialog_id),
                        {
                            "type": "assistant_done",
                            "message": dto.model_dump(mode="json"),
                        },
                    )
                else:
                    draft = await self._persist_draft(
                        dialog_id,
                        message_id,
                        generated_text,
                        confidence,
                        source_snapshot,
                    )
                    await self._broker.publish(
                        operator_dialog_channel(dialog_id),
                        {
                            "type": "draft_done",
                            "draft": draft.model_dump(mode="json"),
                        },
                    )
                await self._record_metric(
                    dialog_id,
                    started,
                    confidence,
                    False,
                    usage,
                    runtime_settings,
                    prompt_version,
                )
        except ProviderPolicyError:
            if dialog_id is not None and mode == DialogMode.AI_SUPPORT:
                try:
                    dto = await self._persist_assistant(
                        dialog_id,
                        (
                            "Не могу обработать этот запрос из-за ограничений "
                            "безопасности. Переформулируйте вопрос в контексте "
                            "технической поддержки 1С."
                        ),
                        None,
                        source_snapshot,
                        trigger_message_id=message_id,
                    )
                    await self._broker.publish(
                        user_dialog_channel(dialog_id),
                        {
                            "type": "assistant_done",
                            "message": dto.model_dump(mode="json"),
                        },
                    )
                    await self._record_metric(
                        dialog_id,
                        started,
                        confidence,
                        False,
                        None,
                        runtime_settings,
                        prompt_version,
                    )
                except Exception:
                    logger.exception(
                        "Unable to persist policy-safe response for message %s",
                        message_id,
                    )
                    await self._mark_turn_failed(
                        message_id, "Не удалось обработать сообщение"
                    )
                    await self._broker.publish(
                        user_dialog_channel(dialog_id),
                        {
                            "type": "error",
                            "message": "Не удалось обработать сообщение",
                        },
                    )
            elif dialog_id is not None:
                await self._mark_turn_failed(
                    message_id,
                    "GigaChat не может обработать запрос из-за "
                    "тематических ограничений",
                )
                await self._broker.publish(
                    operator_dialog_channel(dialog_id),
                    {
                        "type": "error",
                        "message": (
                            "GigaChat не может обработать запрос из-за "
                            "тематических ограничений"
                        ),
                    },
                )
        except ProviderError as exc:
            await self._mark_turn_failed(message_id, str(exc))
            if dialog_id is not None:
                channel = (
                    user_dialog_channel(dialog_id)
                    if mode == DialogMode.AI_SUPPORT
                    else operator_dialog_channel(dialog_id)
                )
                await self._broker.publish(
                    channel, {"type": "error", "message": str(exc)}
                )
        except Exception:
            logger.exception("Dialog turn processing failed for message %s", message_id)
            await self._mark_turn_failed(message_id, "Не удалось обработать сообщение")
            if dialog_id is not None:
                channel = (
                    user_dialog_channel(dialog_id)
                    if mode == DialogMode.AI_SUPPORT
                    else operator_dialog_channel(dialog_id)
                )
                await self._broker.publish(
                    channel,
                    {"type": "error", "message": "Не удалось обработать сообщение"},
                )
        finally:
            if prompt_embedding_task is not None:
                if not prompt_embedding_task.done():
                    prompt_embedding_task.cancel()
                await asyncio.gather(prompt_embedding_task, return_exceptions=True)

    async def read_attachment(
        self, requester: User, attachment_id: uuid.UUID
    ) -> tuple[bytes, str, str]:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Attachment, Dialog)
                    .join(Message, Attachment.message_id == Message.id)
                    .join(Dialog, Message.dialog_id == Dialog.id)
                    .where(Attachment.id == attachment_id)
                )
            ).one_or_none()
            if row is None:
                raise NotFoundError("Вложение не найдено")
            attachment, dialog = row
            self._assert_read_access(requester, dialog)
            try:
                data = await self._attachment_service.storage.get(
                    attachment.storage_key
                )
            except StorageError as exc:
                raise ServiceUnavailableError(
                    "Хранилище вложений временно недоступно"
                ) from exc
            return (
                data,
                attachment.mime_type,
                PurePosixPath(attachment.storage_key).name,
            )

    async def assert_user_sse_access(self, user: User, dialog_id: uuid.UUID) -> None:
        if user.role != UserRole.USER:
            raise ForbiddenError("User SSE доступен только пользователю")
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id)
            if dialog is None:
                raise NotFoundError("Диалог не найден")
            if dialog.user_id != user.id:
                raise ForbiddenError()

    async def assert_operator_sse_access(
        self, operator: User, dialog_id: uuid.UUID
    ) -> None:
        if operator.role != UserRole.OPERATOR:
            raise ForbiddenError("Operator SSE доступен только оператору")
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id)
            if dialog is None:
                raise NotFoundError("Диалог не найден")
            if dialog.mode != DialogMode.OPERATOR_SUPPORT or (
                dialog.assigned_operator_id is not None
                and dialog.assigned_operator_id != operator.id
            ):
                raise ForbiddenError()

    async def _persist_confidence(
        self,
        dialog_id: uuid.UUID,
        message_id: uuid.UUID,
        confidence: float,
        sources: list[dict[str, object]],
    ) -> None:
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id, with_for_update=True)
            message = await session.get(Message, message_id)
            if dialog is None or message is None:
                return
            dialog.dialog_confidence = confidence
            dialog.updated_at = datetime.now(UTC)
            message.confidence = confidence
            message.sources = sources
            await session.commit()

    async def _escalate(
        self,
        dialog_id: uuid.UUID,
        confidence: float,
        sources: list[dict[str, object]],
        started: float,
        runtime_settings: RuntimeSettings,
        prompt_version: int,
        trigger_message_id: uuid.UUID,
    ) -> None:
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id, with_for_update=True)
            if dialog is None or dialog.status != DialogStatus.ACTIVE:
                return
            if dialog.mode == DialogMode.OPERATOR_SUPPORT:
                return
            now = datetime.now(UTC)
            dialog.mode = DialogMode.OPERATOR_SUPPORT
            dialog.escalated_at = now
            dialog.updated_at = now
            system_message = Message(
                dialog_id=dialog_id,
                author_type=MessageAuthor.SYSTEM,
                text=ESCALATION_SYSTEM_MESSAGE,
                confidence=confidence,
                sources=sources,
            )
            session.add(system_message)
            await self._set_trigger_status(
                session,
                trigger_message_id,
                MessageProcessingStatus.COMPLETED,
            )
            await session.commit()
            dto = message_dto(system_message)
            summary = await self._summary(session, dialog, system_message)
        await self._broker.publish(
            user_dialog_channel(dialog_id),
            {
                "type": "operator_connected",
                "message": dto.model_dump(mode="json"),
            },
        )
        await self._broker.publish(
            OPERATOR_QUEUE_CHANNEL,
            {
                "type": "ticket_available",
                "dialog": summary.model_dump(mode="json"),
            },
        )
        await self._record_metric(
            dialog_id,
            started,
            confidence,
            True,
            None,
            runtime_settings,
            prompt_version,
        )

    async def _persist_assistant(
        self,
        dialog_id: uuid.UUID,
        text: str,
        confidence: float | None,
        sources: list[dict[str, object]],
        *,
        trigger_message_id: uuid.UUID | None = None,
    ) -> MessageDto:
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id, with_for_update=True)
            if dialog is None or dialog.status != DialogStatus.ACTIVE:
                raise ConflictError("Диалог уже закрыт")
            message = Message(
                dialog_id=dialog_id,
                author_type=MessageAuthor.ASSISTANT,
                text=text,
                confidence=confidence,
                sources=sources,
            )
            session.add(message)
            if trigger_message_id is not None:
                await self._set_trigger_status(
                    session,
                    trigger_message_id,
                    MessageProcessingStatus.COMPLETED,
                )
            dialog.updated_at = datetime.now(UTC)
            await session.commit()
            return message_dto(message)

    async def _persist_draft(
        self,
        dialog_id: uuid.UUID,
        trigger_message_id: uuid.UUID,
        text: str,
        confidence: float,
        sources: list[dict[str, object]],
    ) -> OperatorDraftDto:
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(OperatorDraft).where(
                    OperatorDraft.trigger_message_id == trigger_message_id
                )
            )
            if existing is not None:
                await self._set_trigger_status(
                    session,
                    trigger_message_id,
                    MessageProcessingStatus.COMPLETED,
                )
                await session.commit()
                return draft_dto(existing)
            draft = OperatorDraft(
                dialog_id=dialog_id,
                trigger_message_id=trigger_message_id,
                text=text,
                confidence=confidence,
                sources=sources,
            )
            session.add(draft)
            await self._set_trigger_status(
                session,
                trigger_message_id,
                MessageProcessingStatus.COMPLETED,
            )
            dialog = await session.get(Dialog, dialog_id)
            if dialog is not None:
                dialog.updated_at = datetime.now(UTC)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(OperatorDraft).where(
                        OperatorDraft.trigger_message_id == trigger_message_id
                    )
                )
                if existing is None:
                    raise
                await self._set_trigger_status(
                    session,
                    trigger_message_id,
                    MessageProcessingStatus.COMPLETED,
                )
                dialog = await session.get(Dialog, dialog_id)
                if dialog is not None:
                    dialog.updated_at = datetime.now(UTC)
                await session.commit()
                return draft_dto(existing)
            return draft_dto(draft)

    @staticmethod
    async def _set_trigger_status(
        session: AsyncSession,
        message_id: uuid.UUID,
        status: MessageProcessingStatus,
        error: str | None = None,
    ) -> None:
        trigger = await session.get(Message, message_id)
        if trigger is None or trigger.author_type != MessageAuthor.USER:
            return
        trigger.processing_status = status
        trigger.processing_error = error

    async def _mark_turn_failed(self, message_id: uuid.UUID, error: str) -> None:
        try:
            async with self._session_factory() as session:
                trigger = await session.get(Message, message_id)
                if (
                    trigger is None
                    or trigger.author_type != MessageAuthor.USER
                    or trigger.processing_status == MessageProcessingStatus.COMPLETED
                ):
                    return
                trigger.processing_status = MessageProcessingStatus.FAILED
                trigger.processing_error = error[:4000]
                dialog = await session.get(Dialog, trigger.dialog_id)
                if dialog is not None:
                    dialog.updated_at = datetime.now(UTC)
                await session.commit()
        except Exception:
            logger.exception("Unable to persist processing failure for %s", message_id)

    async def _record_metric(
        self,
        dialog_id: uuid.UUID,
        started: float,
        confidence: float | None,
        escalated: bool,
        usage: ProviderUsage | None,
        runtime_settings: RuntimeSettings | None,
        prompt_version: int | None,
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                MetricEvent(
                    dialog_id=dialog_id,
                    latency_ms=max(0, round((time.monotonic() - started) * 1000)),
                    confidence=confidence,
                    escalated=escalated,
                    prompt_tokens=usage.prompt_tokens if usage else None,
                    completion_tokens=usage.completion_tokens if usage else None,
                    precached_prompt_tokens=(
                        usage.precached_prompt_tokens if usage else None
                    ),
                    gigachat_model=(
                        runtime_settings.active_model if runtime_settings else None
                    ),
                    system_prompt_version=prompt_version,
                    rag_top_k=(
                        runtime_settings.rag_top_k if runtime_settings else None
                    ),
                    operator_escalation_threshold=(
                        runtime_settings.operator_escalation_threshold
                        if runtime_settings
                        else None
                    ),
                )
            )
            await session.commit()

    @staticmethod
    async def _turn_completed(
        session: AsyncSession,
        trigger: Message,
        dialog: Dialog,
    ) -> bool:
        if trigger.processing_status in {
            MessageProcessingStatus.COMPLETED,
            MessageProcessingStatus.FAILED,
        }:
            return True
        draft_id = await session.scalar(
            select(OperatorDraft.id)
            .where(OperatorDraft.trigger_message_id == trigger.id)
            .limit(1)
        )
        if draft_id is not None:
            return True
        assistant_id = await session.scalar(
            select(Message.id)
            .where(
                Message.dialog_id == trigger.dialog_id,
                Message.author_type == MessageAuthor.ASSISTANT,
                Message.created_at > trigger.created_at,
            )
            .limit(1)
        )
        if assistant_id is not None:
            return True
        if dialog.mode == DialogMode.OPERATOR_SUPPORT:
            operator_message_id = await session.scalar(
                select(Message.id)
                .where(
                    Message.dialog_id == trigger.dialog_id,
                    Message.author_type == MessageAuthor.OPERATOR,
                    Message.created_at > trigger.created_at,
                )
                .limit(1)
            )
            if operator_message_id is not None:
                return True
            escalation_id = await session.scalar(
                select(Message.id)
                .where(
                    Message.dialog_id == trigger.dialog_id,
                    Message.author_type == MessageAuthor.SYSTEM,
                    Message.text == ESCALATION_SYSTEM_MESSAGE,
                    Message.created_at > trigger.created_at,
                )
                .limit(1)
            )
            return escalation_id is not None
        return False

    async def _processing_state(
        self, session: AsyncSession, dialog: Dialog
    ) -> tuple[bool, str | None]:
        if dialog.status != DialogStatus.ACTIVE:
            return False, None
        trigger = await session.scalar(
            select(Message)
            .where(
                Message.dialog_id == dialog.id,
                Message.author_type == MessageAuthor.USER,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        if trigger is None:
            return False, None
        if trigger.processing_status == MessageProcessingStatus.FAILED:
            return False, trigger.processing_error
        if await self._turn_completed(session, trigger, dialog):
            return False, None
        if trigger.processing_status in {
            MessageProcessingStatus.PENDING,
            MessageProcessingStatus.PROCESSING,
        }:
            return True, None
        return True, None

    async def _detail(
        self,
        session: AsyncSession,
        requester: User,
        dialog: Dialog,
    ) -> DialogDetail:
        owner = await session.get(User, dialog.user_id)
        if owner is None:
            raise NotFoundError("Владелец диалога не найден")
        operator = (
            await session.get(User, dialog.assigned_operator_id)
            if dialog.assigned_operator_id
            else None
        )
        last = await session.scalar(
            select(Message)
            .where(Message.dialog_id == dialog.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        first_user_message = await session.scalar(
            select(Message)
            .where(
                Message.dialog_id == dialog.id,
                Message.author_type == MessageAuthor.USER,
            )
            .order_by(Message.created_at, Message.id)
            .limit(1)
        )
        feedback = await session.scalar(
            select(DialogFeedback).where(DialogFeedback.dialog_id == dialog.id)
        )
        candidate = await session.scalar(
            select(KnowledgeCandidate).where(KnowledgeCandidate.dialog_id == dialog.id)
        )
        has_attachment = (
            await session.scalar(
                select(Attachment.id)
                .join(Message, Attachment.message_id == Message.id)
                .where(Message.dialog_id == dialog.id)
                .limit(1)
            )
            is not None
        )
        latest_draft = None
        if requester.role == UserRole.OPERATOR:
            latest_draft = await session.scalar(
                select(OperatorDraft)
                .where(OperatorDraft.dialog_id == dialog.id)
                .order_by(OperatorDraft.created_at.desc(), OperatorDraft.id.desc())
                .limit(1)
            )
        is_processing, processing_error = await self._processing_state(session, dialog)
        return dialog_detail(
            dialog,
            owner,
            last,
            operator,
            first_user_message=first_user_message,
            has_attachment=has_attachment,
            is_processing=is_processing,
            processing_error=processing_error,
            feedback=feedback,
            candidate=candidate,
            latest_draft=latest_draft,
        )

    async def _summary(
        self,
        session: AsyncSession,
        dialog: Dialog,
        last: Message | None = None,
    ) -> DialogSummary:
        if last is None:
            last = await session.scalar(
                select(Message)
                .where(Message.dialog_id == dialog.id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(1)
            )
        is_processing, processing_error = await self._processing_state(session, dialog)
        operator = (
            await session.get(User, dialog.assigned_operator_id)
            if dialog.assigned_operator_id
            else None
        )
        owner = await session.get(User, dialog.user_id)
        first_user_message = await session.scalar(
            select(Message)
            .where(
                Message.dialog_id == dialog.id,
                Message.author_type == MessageAuthor.USER,
            )
            .order_by(Message.created_at, Message.id)
            .limit(1)
        )
        feedback = await session.scalar(
            select(DialogFeedback).where(DialogFeedback.dialog_id == dialog.id)
        )
        candidate = await session.scalar(
            select(KnowledgeCandidate).where(KnowledgeCandidate.dialog_id == dialog.id)
        )
        has_attachment = (
            await session.scalar(
                select(Attachment.id)
                .join(Message, Attachment.message_id == Message.id)
                .where(Message.dialog_id == dialog.id)
                .limit(1)
            )
            is not None
        )
        return dialog_summary(
            dialog,
            last,
            operator,
            owner=owner,
            first_user_message=first_user_message,
            has_attachment=has_attachment,
            is_processing=is_processing,
            processing_error=processing_error,
            feedback=feedback,
            candidate=candidate,
        )

    @staticmethod
    async def _attachments_by_message(
        session: AsyncSession, message_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[Attachment]]:
        if not message_ids:
            return {}
        attachments = list(
            await session.scalars(
                select(Attachment).where(Attachment.message_id.in_(message_ids))
            )
        )
        result: dict[uuid.UUID, list[Attachment]] = {}
        for attachment in attachments:
            result.setdefault(attachment.message_id, []).append(attachment)
        return result

    @staticmethod
    def _history(
        messages: list[Message],
        attachments: dict[uuid.UUID, list[Attachment]],
    ) -> list[ChatTurn]:
        history: list[ChatTurn] = []
        for message in messages:
            text = message.text
            for attachment in attachments.get(message.id, []):
                if attachment.extracted_text:
                    text += f"\n[Текст вложения] {attachment.extracted_text}"
                if attachment.visual_summary:
                    text += f"\n[Описание вложения] {attachment.visual_summary}"
            history.append(ChatTurn(role=message.author_type.value, text=text))
        return history

    @staticmethod
    def _assert_read_access(requester: User, dialog: Dialog) -> None:
        if requester.role == UserRole.ADMIN:
            return
        if requester.role == UserRole.USER:
            if dialog.user_id != requester.id:
                raise ForbiddenError()
            return
        if requester.role == UserRole.OPERATOR:
            if dialog.mode != DialogMode.OPERATOR_SUPPORT:
                raise ForbiddenError()
            if (
                dialog.assigned_operator_id is not None
                and dialog.assigned_operator_id != requester.id
            ):
                raise ForbiddenError()
            return
        raise ForbiddenError()

    @staticmethod
    def _assert_send_access(requester: User, dialog: Dialog) -> None:
        if dialog.status != DialogStatus.ACTIVE:
            raise ConflictError("Диалог уже закрыт")
        if requester.role == UserRole.USER:
            if dialog.user_id != requester.id:
                raise ForbiddenError()
            return
        if requester.role == UserRole.OPERATOR:
            if (
                dialog.mode != DialogMode.OPERATOR_SUPPORT
                or dialog.assigned_operator_id != requester.id
            ):
                raise ForbiddenError("Отправлять ответ может назначенный оператор")
            return
        raise ForbiddenError()
