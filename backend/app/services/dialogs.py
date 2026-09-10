from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from sqlalchemy import and_, case, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.mappers import (
    dialog_detail,
    dialog_summary,
    message_dto,
)
from app.contracts.schemas import (
    DialogDetail,
    DialogSummary,
    MessageDto,
    MessagePage,
    OperatorTemplateDto,
)
from app.core.constants import ESCALATION_SYSTEM_MESSAGE
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
from app.core.generation_gate import GenerationGate
from app.core.turn_coordinator import (
    AI_TURN_ADMISSION_LOCK_KEY,
    TurnCoordinator,
)
from app.models import (
    Attachment,
    Dialog,
    DialogFeedback,
    KnowledgeCandidate,
    Message,
    MetricEvent,
    User,
)
from app.providers.interfaces import (
    LLMProvider,
    ProviderError,
    ProviderServerError,
    ProviderUsage,
    StorageError,
)
from app.services.attachments import (
    AttachmentService,
    ValidatedUpload,
)
from app.services.broker import (
    OPERATOR_QUEUE_CHANNEL,
    EventBroker,
    operator_dialog_channel,
    user_dialog_channel,
)
from app.services.generation_context import GenerationContextService
from app.services.model_output import ModelOutputStreamFilter
from app.services.settings import PromptService, RuntimeSettings, SettingsService
from app.services.tasks import TaskSupervisor

logger = logging.getLogger(__name__)
LOW_CONFIDENCE_ESCALATION_STREAK = 3
AI_PROCESSING_ADVISORY_LOCK_KEY = 712031045
_OPERATOR_REQUEST_MARKERS = (
    "подключите оператора",
    "подключите живого оператора",
    "подключите живого специалиста",
    "подключи оператора",
    "подключи специалиста",
    "позовите оператора",
    "позови оператора",
    "хочу специалиста",
    "соедините с оператором",
    "соедините с поддержкой",
    "соедините меня с поддержкой",
    "соедините меня с оператором",
    "соедините меня со специалистом",
    "переключите на оператора",
    "переведите на оператора",
    "переведи на оператора",
    "переведи на специалиста",
    "переведи к оператору",
    "переведи к специалисту",
    "переведите на специалиста",
    "переведите к специалисту",
    "соедини с оператором",
    "соедини со специалистом",
    "хочу поговорить с оператором",
    "нужен оператор",
    "нужен специалист",
    "мне нужен человек",
    "мне нужен живой оператор",
    "позовите специалиста",
    "позови специалиста",
    "подключите специалиста",
    "передайте оператору",
    "передай оператору",
    "передай специалисту",
    "хочу поговорить с человеком",
)
_OPERATOR_REQUEST_NEGATIONS = (
    "не нужен оператор",
    "оператор не нужен",
    "не хочу оператора",
    "не нужен специалист",
    "специалист не нужен",
    "не подключайте оператора",
    "не подключайте специалиста",
)


class DialogService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        attachment_service: AttachmentService,
        settings_service: SettingsService,
        prompt_service: PromptService,
        generation_context: GenerationContextService,
        llm_provider: LLMProvider,
        broker: EventBroker,
        tasks: TaskSupervisor,
        generation_gate: GenerationGate,
        turn_coordinator: TurnCoordinator | None = None,
        ensure_closed_candidate: Callable[[AsyncSession, uuid.UUID], Awaitable[object]]
        | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._attachment_service = attachment_service
        self._settings_service = settings_service
        self._prompt_service = prompt_service
        self._generation_context = generation_context
        self._llm_provider = llm_provider
        self._broker = broker
        self._tasks = tasks
        self._generation_gate = generation_gate
        self._turn_coordinator = turn_coordinator or TurnCoordinator()
        self._ensure_closed_candidate = ensure_closed_candidate
        self._dialog_locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._processing_message_ids: set[uuid.UUID] = set()

    def dialog_lock(self, dialog_id: uuid.UUID) -> asyncio.Lock:
        return self._dialog_locks.setdefault(dialog_id, asyncio.Lock())

    def _schedule_processing(
        self,
        message_id: uuid.UUID,
        dialog_id: uuid.UUID,
        mode: DialogMode,
    ) -> None:
        if mode != DialogMode.AI_SUPPORT:
            return
        if message_id in self._processing_message_ids:
            return
        if not self._turn_coordinator.try_acquire(dialog_id, message_id):
            return
        self._processing_message_ids.add(message_id)

        async def run() -> None:
            try:
                await self.process_user_message(message_id)
            finally:
                self._processing_message_ids.discard(message_id)
                self._turn_coordinator.release(dialog_id, message_id)
                if self._tasks.accepting:
                    await self._schedule_next_pending_turn()

        if not self._tasks.spawn(run()):
            self._processing_message_ids.discard(message_id)
            self._turn_coordinator.release(dialog_id, message_id)

    async def recover_pending_turns(self) -> None:
        async with self._processing_lock() as acquired:
            if not acquired:
                return
            await self._recover_processing_rows()
        await self._schedule_next_pending_turn()

    async def recover_pending_turns_loop(self, scan_interval_seconds: float) -> None:
        while True:
            try:
                await self.recover_pending_turns()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("AI turn recovery sweep failed")
            await asyncio.sleep(scan_interval_seconds)

    async def _recover_processing_rows(self) -> None:
        async with self._session_factory() as session:
            triggers = list(
                await session.scalars(
                    select(Message)
                    .join(Dialog, Message.dialog_id == Dialog.id)
                    .where(
                        Dialog.status == DialogStatus.ACTIVE,
                        Dialog.mode == DialogMode.AI_SUPPORT,
                        Message.author_type == MessageAuthor.USER,
                        Message.processing_status.in_(
                            [
                                MessageProcessingStatus.PENDING,
                                MessageProcessingStatus.PROCESSING,
                            ]
                        ),
                    )
                    .order_by(Message.created_at, Message.id)
                )
            )
            changed = False
            for trigger in triggers:
                if await self._turn_completed(session, trigger):
                    continue
                if trigger.processing_status == MessageProcessingStatus.PROCESSING:
                    trigger.processing_status = MessageProcessingStatus.PENDING
                    trigger.processing_error = None
                    changed = True
            if changed:
                await session.commit()

    @asynccontextmanager
    async def _processing_lock(self) -> AsyncIterator[bool]:
        async with self._session_factory() as session:
            bind = session.bind
            if bind is None or bind.dialect.name != "postgresql":
                yield True
                return
            acquired = bool(
                await session.scalar(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": AI_PROCESSING_ADVISORY_LOCK_KEY},
                )
            )
            try:
                yield acquired
            finally:
                if acquired:
                    await session.execute(
                        text("SELECT pg_advisory_unlock(:lock_key)"),
                        {"lock_key": AI_PROCESSING_ADVISORY_LOCK_KEY},
                    )

    async def create_dialog(self, user: User) -> DialogDetail:
        if user.role != UserRole.USER:
            raise ForbiddenError("Создавать обращения может только пользователь")
        async with self._session_factory() as session:
            await self._assert_no_active_ai_turn(session)
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

    async def discard_empty_dialog(self, user: User, dialog_id: uuid.UUID) -> None:
        if user.role != UserRole.USER:
            raise ForbiddenError("Endpoint доступен только пользователю")
        async with self.dialog_lock(dialog_id):
            async with self._session_factory() as session:
                dialog = await session.get(Dialog, dialog_id, with_for_update=True)
                if dialog is None:
                    raise NotFoundError("Диалог не найден")
                if dialog.user_id != user.id:
                    raise ForbiddenError()
                has_messages = await session.scalar(
                    select(Message.id).where(Message.dialog_id == dialog_id).limit(1)
                )
                if has_messages is not None:
                    raise ConflictError("Черновик уже содержит сообщение")
                await session.delete(dialog)
                await session.commit()

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
                    .order_by(
                        case(
                            (Dialog.status == DialogStatus.CLOSED, 1),
                            else_=0,
                        ),
                        Dialog.updated_at.desc(),
                        Dialog.id.desc(),
                    )
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
            operator = (
                await session.get(User, dialog.assigned_operator_id)
                if dialog.assigned_operator_id
                else None
            )
            return MessagePage(
                items=[
                    message_dto(
                        message,
                        attachments.get(message.id, []),
                        operator
                        if message.author_type == MessageAuthor.OPERATOR
                        else None,
                    )
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
            # Serialize validation and commit with close() across all workers.
            dialog = await session.get(Dialog, dialog_id, with_for_update=True)
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
                    and dialog.mode == DialogMode.AI_SUPPORT
                ):
                    if existing.processing_status == MessageProcessingStatus.FAILED:
                        await self._reserve_ai_turn(
                            session,
                            dialog_id,
                            existing.id,
                            exclude_message_id=existing.id,
                        )
                        try:
                            existing.processing_status = MessageProcessingStatus.PENDING
                            existing.processing_error = None
                            await session.commit()
                        except Exception:
                            self._turn_coordinator.release(dialog_id, existing.id)
                            raise
                    if not defer_processing:
                        self._schedule_processing(existing.id, dialog_id, dialog.mode)
                return message_dto(
                    existing,
                    existing_attachments.get(existing.id, []),
                    requester if requester.role == UserRole.OPERATOR else None,
                ), False

            self._assert_send_access(requester, dialog)

            if requester.role == UserRole.USER and dialog.mode != DialogMode.AI_SUPPORT:
                await self._assert_no_active_ai_turn(session)
            message_id = uuid.uuid4()
            reserved_turn = (
                requester.role == UserRole.USER and dialog.mode == DialogMode.AI_SUPPORT
            )
            if reserved_turn:
                await self._reserve_ai_turn(session, dialog_id, message_id)
            message = Message(
                id=message_id,
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
                    if (
                        requester.role == UserRole.USER
                        and dialog.mode == DialogMode.AI_SUPPORT
                    )
                    else None
                ),
            )
            session.add(message)
            try:
                await session.flush()
            except IntegrityError as exc:
                await session.rollback()
                if reserved_turn:
                    self._turn_coordinator.release(dialog_id, message_id)
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
                    existing,
                    existing_attachments.get(existing.id, []),
                    requester if requester.role == UserRole.OPERATOR else None,
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
                            size_bytes=upload.size_bytes,
                        )
                    )
                    stored_keys.append(storage_key)
                session.add_all(attachments)
                dialog.updated_at = datetime.now(UTC)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                if reserved_turn:
                    self._turn_coordinator.release(dialog_id, message_id)
                if stored_keys:
                    await self._attachment_service.cleanup_local(stored_keys)
                if isinstance(exc, StorageError):
                    raise ServiceUnavailableError(
                        "Хранилище вложений временно недоступно"
                    ) from exc
                raise
            dto = message_dto(
                message,
                attachments,
                requester if requester.role == UserRole.OPERATOR else None,
            )
            mode = dialog.mode

        payload = dto.model_dump(mode="json")
        if requester.role == UserRole.USER:
            if mode == DialogMode.OPERATOR_SUPPORT:
                await self._broker.publish(
                    operator_dialog_channel(dialog_id),
                    {"type": "user_message", "message": payload},
                )
                async with self._session_factory() as session:
                    current_dialog = await session.get(Dialog, dialog_id)
                    summary = (
                        await self._summary(session, current_dialog)
                        if current_dialog is not None
                        else None
                    )
                if summary is not None:
                    await self._broker.publish(
                        OPERATOR_QUEUE_CHANNEL,
                        {
                            "type": "ticket_updated",
                            "dialog": summary.model_dump(mode="json"),
                        },
                    )
            if not defer_processing and mode == DialogMode.AI_SUPPORT:
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
            if dialog.mode != DialogMode.AI_SUPPORT:
                return
            if await self._turn_completed(session, message):
                return
            mode = dialog.mode
        self._schedule_processing(message_id, message.dialog_id, mode)

    async def _schedule_next_pending_turn(self) -> None:
        """Resume one persisted turn after the global turn becomes available."""
        async with self._session_factory() as session:
            if (
                await self._find_active_ai_turn(session, include_pending=False)
                is not None
            ):
                return
            triggers = list(
                await session.scalars(
                    select(Message)
                    .join(Dialog, Message.dialog_id == Dialog.id)
                    .where(
                        Dialog.status == DialogStatus.ACTIVE,
                        Dialog.mode == DialogMode.AI_SUPPORT,
                        Message.author_type == MessageAuthor.USER,
                        Message.processing_status.in_(
                            [
                                MessageProcessingStatus.PENDING,
                                MessageProcessingStatus.PROCESSING,
                            ]
                        ),
                    )
                    .order_by(Message.created_at, Message.id)
                )
            )
            for trigger in triggers:
                if await self._turn_completed(session, trigger):
                    continue
                self._schedule_processing(
                    trigger.id, trigger.dialog_id, DialogMode.AI_SUPPORT
                )
                return

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
                await session.scalars(
                    statement.order_by(Dialog.updated_at.desc(), Dialog.id.desc())
                )
            )
            return [await self._summary(session, dialog) for dialog in dialogs]

    async def generate_operator_template(
        self, operator: User, dialog_id: uuid.UUID
    ) -> OperatorTemplateDto:
        if operator.role != UserRole.OPERATOR:
            raise ForbiddenError("Endpoint доступен только оператору")

        started = time.monotonic()
        runtime_settings: RuntimeSettings | None = None
        prompt_content: str | None = None
        usage: ProviderUsage | None = None
        success = False
        error_message: str | None = None
        try:
            async with self.dialog_lock(dialog_id):
                async with self._session_factory() as session:
                    dialog = await session.get(Dialog, dialog_id)
                    if dialog is None:
                        raise NotFoundError("Диалог не найден")
                    self._assert_send_access(operator, dialog)
                    dialog_updated_at = dialog.updated_at
                    runtime_settings = await self._settings_service.get_runtime(session)
                    prompt = await self._prompt_service.get_active(
                        session, PromptType.OPERATOR_GIGACHAT
                    )
                    prompt_content = prompt.content
                async with self._generation_gate.acquire():
                    context = (
                        await self._generation_context.build_for_operator_template(
                            dialog_id=dialog_id,
                            system_prompt=prompt.content,
                            settings=runtime_settings,
                        )
                    )
                    output_filter = ModelOutputStreamFilter()
                    async for chunk in self._llm_provider.stream_text(
                        context.request,
                        runtime_settings.active_model,
                        runtime_settings.gigachat_max_output_tokens,
                        dialog_id,
                    ):
                        if chunk.usage is not None:
                            usage = chunk.usage
                        if chunk.text:
                            output_filter.push(chunk.text)
                    generated_text = output_filter.final()
                    if not generated_text:
                        raise ProviderServerError("GigaChat вернул пустой шаблон")
                success = True
                return OperatorTemplateDto(
                    dialog_id=dialog_id,
                    dialog_updated_at=dialog_updated_at,
                    text=generated_text,
                    created_at=datetime.now(UTC),
                )
        except ProviderError as exc:
            error_message = str(exc)
            raise ServiceUnavailableError(str(exc)) from exc
        except Exception as exc:
            error_message = str(exc)
            raise
        finally:
            await self._record_metric(
                dialog_id,
                started,
                None,
                False,
                usage,
                runtime_settings,
                prompt_content,
                event_type="operator_template",
                success=success,
                error_message=error_message,
            )

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
        await self._broker.publish(
            operator_dialog_channel(dialog_id),
            {
                "type": "operator_access_revoked",
                "operator": {
                    "id": str(operator.id),
                    "display_name": operator.display_name,
                },
            },
        )
        return detail

    async def close(self, requester: User, dialog_id: uuid.UUID) -> DialogDetail:
        async with self.dialog_lock(dialog_id):
            async with self._session_factory() as session:
                dialog = await session.get(Dialog, dialog_id, with_for_update=True)
                if dialog is None:
                    raise NotFoundError("Диалог не найден")
                if dialog.status == DialogStatus.CLOSED:
                    raise ConflictError("Диалог уже закрыт")
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

                mode = await self._finalize_close(session, dialog)
                await session.commit()

            await self._publish_dialog_closed(dialog_id, mode)
            return await self.get_dialog(requester, dialog_id)

    async def close_idle_dialogs_loop(
        self, *, idle_after: timedelta, scan_interval_seconds: float
    ) -> None:
        """Close inactive AI dialogs while the application is running."""
        while True:
            try:
                closed = await self.close_idle_dialogs(idle_after)
                if closed:
                    logger.info("Automatically closed %d idle AI dialogs", closed)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Idle dialog sweep failed")
            await asyncio.sleep(scan_interval_seconds)

    async def close_idle_dialogs(self, idle_after: timedelta) -> int:
        cutoff = datetime.now(UTC) - idle_after
        async with self._session_factory() as session:
            dialog_ids = list(
                await session.scalars(
                    select(Dialog.id).where(
                        Dialog.status == DialogStatus.ACTIVE,
                        Dialog.mode == DialogMode.AI_SUPPORT,
                    )
                )
            )

        closed = 0
        for dialog_id in dialog_ids:
            try:
                if await self._close_idle_dialog(dialog_id, cutoff):
                    closed += 1
            except Exception:
                logger.exception("Unable to auto-close idle dialog %s", dialog_id)
        return closed

    async def _close_idle_dialog(self, dialog_id: uuid.UUID, cutoff: datetime) -> bool:
        async with self.dialog_lock(dialog_id):
            async with self._session_factory() as session:
                dialog = await session.get(Dialog, dialog_id, with_for_update=True)
                if (
                    dialog is None
                    or dialog.status != DialogStatus.ACTIVE
                    or dialog.mode != DialogMode.AI_SUPPORT
                ):
                    return False
                latest = await session.scalar(
                    select(Message)
                    .where(
                        Message.dialog_id == dialog_id,
                        Message.author_type != MessageAuthor.SYSTEM,
                    )
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(1)
                )
                last_activity = latest.created_at if latest else dialog.created_at
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=UTC)
                if last_activity >= cutoff:
                    return False
                if latest is not None and latest.author_type == MessageAuthor.USER:
                    if latest.processing_status in {
                        MessageProcessingStatus.PENDING,
                        MessageProcessingStatus.PROCESSING,
                    }:
                        return False
                mode = await self._finalize_close(session, dialog)
                await session.commit()
            await self._publish_dialog_closed(dialog_id, mode)
            return True

    async def _finalize_close(
        self, session: AsyncSession, dialog: Dialog
    ) -> DialogMode:
        settings = await self._settings_service.get_runtime(session)
        remote_attachments = list(
            await session.scalars(
                select(Attachment)
                .join(Message, Attachment.message_id == Message.id)
                .where(
                    Message.dialog_id == dialog.id,
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
                async with self._generation_gate.acquire():
                    await self._attachment_service.cleanup_remote(
                        remote_ids, settings.active_model, dialog.id
                    )
            except ProviderError as exc:
                raise ServiceUnavailableError(str(exc)) from exc

        closed_at = datetime.now(UTC)
        dialog.status = DialogStatus.CLOSED
        dialog.closed_at = closed_at
        dialog.updated_at = closed_at
        if self._ensure_closed_candidate is not None:
            await self._ensure_closed_candidate(session, dialog.id)
        if remote_ids:
            attachments = list(
                await session.scalars(
                    select(Attachment)
                    .join(Message, Attachment.message_id == Message.id)
                    .where(
                        Message.dialog_id == dialog.id,
                        Attachment.gigachat_file_id.in_(remote_ids),
                    )
                )
            )
            for attachment in attachments:
                attachment.remote_deleted_at = closed_at
        return dialog.mode

    async def _publish_dialog_closed(
        self, dialog_id: uuid.UUID, mode: DialogMode
    ) -> None:
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

    async def process_user_message(self, message_id: uuid.UUID) -> None:
        async with self._processing_lock() as acquired:
            if not acquired:
                return
            await self._recover_processing_rows()
            await self._process_user_message_owned(message_id)

    async def _process_user_message_owned(self, message_id: uuid.UUID) -> None:
        started = time.monotonic()
        dialog_id: uuid.UUID | None = None
        confidence: float | None = None
        source_snapshot: list[dict[str, object]] = []
        runtime_settings: RuntimeSettings | None = None
        prompt_content: str | None = None
        usage: ProviderUsage | None = None
        trigger_text = ""
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
                    if dialog.mode != DialogMode.AI_SUPPORT:
                        return
                    if trigger.processing_status != MessageProcessingStatus.PENDING:
                        return
                    if await self._turn_completed(session, trigger):
                        return
                    await self._lock_turn_admission(session)
                    trigger = await session.get(
                        Message, message_id, with_for_update=True
                    )
                    if (
                        trigger is None
                        or trigger.processing_status != MessageProcessingStatus.PENDING
                    ):
                        return
                    if (
                        await self._find_active_ai_turn(
                            session,
                            exclude_message_id=message_id,
                            include_pending=False,
                        )
                        is not None
                    ):
                        return
                    trigger_text = trigger.text
                    trigger.processing_status = MessageProcessingStatus.PROCESSING
                    trigger.processing_error = None
                    dialog.updated_at = datetime.now(UTC)
                    await session.commit()
                    runtime_settings = await self._settings_service.get_runtime(session)
                    prompt = await self._prompt_service.get_active(
                        session, PromptType.USER_SUPPORT
                    )
                    prompt_content = prompt.content

                if self._explicit_operator_request(trigger_text):
                    confidence = 0.0
                    await self._persist_confidence(
                        dialog_id, message_id, confidence, []
                    )
                    await self._broker.publish(
                        user_dialog_channel(dialog_id),
                        {"type": "confidence", "value": confidence},
                    )
                    await self._escalate(
                        dialog_id,
                        confidence,
                        [],
                        started,
                        runtime_settings,
                        prompt_content,
                        message_id,
                        usage=None,
                    )
                    return

                async with self._generation_gate.acquire():
                    context = await self._generation_context.build_for_user_message(
                        dialog_id=dialog_id,
                        message_id=message_id,
                        system_prompt=prompt.content,
                        settings=runtime_settings,
                    )
                    generation_request = context.request
                    logger.info(
                        "RAG retrieval status=%s evidence_count=%d dialog=%s",
                        generation_request.rag_status,
                        len(generation_request.evidence),
                        dialog_id,
                    )
                    source_snapshot = [
                        item.source.model_dump(mode="json")
                        for item in generation_request.evidence
                    ]

                    assessment = await self._llm_provider.evaluate_confidence(
                        generation_request,
                        runtime_settings.active_model,
                        dialog_id,
                    )
                    confidence = assessment.confidence
                    usage = self._combine_usage(getattr(assessment, "usage", None))
                    await self._persist_confidence(
                        dialog_id, message_id, confidence, source_snapshot
                    )
                    await self._broker.publish(
                        user_dialog_channel(dialog_id),
                        {"type": "confidence", "value": confidence},
                    )

                    if (
                        await self._low_confidence_streak(
                            dialog_id,
                            message_id,
                            runtime_settings.operator_escalation_threshold,
                        )
                        >= LOW_CONFIDENCE_ESCALATION_STREAK
                    ):
                        await self._escalate(
                            dialog_id,
                            confidence,
                            source_snapshot,
                            started,
                            runtime_settings,
                            prompt_content,
                            message_id,
                            usage=usage,
                        )
                        return

                    output_filter = ModelOutputStreamFilter()
                    streamed_text = ""
                    answer_usage: ProviderUsage | None = None
                    async for chunk in self._llm_provider.stream_user_answer(
                        generation_request,
                        runtime_settings.active_model,
                        runtime_settings.gigachat_max_output_tokens,
                        dialog_id,
                    ):
                        if chunk.usage is not None:
                            answer_usage = chunk.usage
                            usage = self._combine_usage(
                                getattr(assessment, "usage", None), answer_usage
                            )
                        if not chunk.text:
                            continue
                        token = output_filter.push(chunk.text)
                        if not token:
                            continue
                        streamed_text += token
                        await self._broker.publish(
                            user_dialog_channel(dialog_id),
                            {"type": "assistant_token", "token": token},
                        )
                    answer_text = output_filter.final()
                    if not answer_text:
                        raise ProviderServerError("GigaChat вернул пустой ответ")
                    if answer_text.startswith(streamed_text):
                        remaining = answer_text[len(streamed_text) :]
                        if remaining:
                            await self._broker.publish(
                                user_dialog_channel(dialog_id),
                                {"type": "assistant_token", "token": remaining},
                            )
                    usage = self._combine_usage(
                        getattr(assessment, "usage", None), answer_usage
                    )
                    dto = await self._persist_assistant(
                        dialog_id,
                        answer_text,
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
                    await self._record_metric(
                        dialog_id,
                        started,
                        confidence,
                        False,
                        usage,
                        runtime_settings,
                        prompt_content,
                    )
        except asyncio.CancelledError:
            await self._mark_turn_pending(message_id)
            raise
        except ProviderError as exc:
            await self._mark_turn_failed(message_id, str(exc))
            if dialog_id is not None:
                await self._record_metric(
                    dialog_id,
                    started,
                    confidence,
                    False,
                    usage,
                    runtime_settings,
                    prompt_content,
                    success=False,
                    error_message=str(exc),
                )
                await self._broker.publish(
                    user_dialog_channel(dialog_id),
                    {"type": "error", "message": str(exc)},
                )
        except Exception:
            logger.exception("Dialog turn processing failed for message %s", message_id)
            await self._mark_turn_failed(message_id, "Не удалось обработать сообщение")
            if dialog_id is not None:
                await self._record_metric(
                    dialog_id,
                    started,
                    confidence,
                    False,
                    usage,
                    runtime_settings,
                    prompt_content,
                    success=False,
                    error_message="Не удалось обработать сообщение",
                )
                await self._broker.publish(
                    user_dialog_channel(dialog_id),
                    {"type": "error", "message": "Не удалось обработать сообщение"},
                )

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
            if not await self.has_operator_sse_access(operator, dialog_id):
                raise ForbiddenError()

    async def has_operator_sse_access(
        self, operator: User, dialog_id: uuid.UUID
    ) -> bool:
        if operator.role != UserRole.OPERATOR:
            return False
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id)
            if dialog is None:
                return False
            return (
                dialog.status == DialogStatus.ACTIVE
                and dialog.mode == DialogMode.OPERATOR_SUPPORT
                and (
                    dialog.assigned_operator_id is None
                    or dialog.assigned_operator_id == operator.id
                )
            )

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

    async def _assert_no_active_ai_turn(self, session: AsyncSession) -> None:
        active = self._turn_coordinator.active
        if active is not None:
            raise ConflictError(
                "Дождитесь завершения обработки сообщения в другом чате",
                {"dialog_id": str(active.dialog_id)},
            )
        await self._lock_turn_admission(session)
        database_active = await self._find_active_ai_turn(session)
        if database_active is not None:
            raise ConflictError(
                "Дождитесь завершения обработки сообщения в другом чате",
                {"dialog_id": str(database_active[0])},
            )

    async def _reserve_ai_turn(
        self,
        session: AsyncSession,
        dialog_id: uuid.UUID,
        message_id: uuid.UUID,
        *,
        exclude_message_id: uuid.UUID | None = None,
    ) -> None:
        if not self._turn_coordinator.try_acquire(dialog_id, message_id):
            active = self._turn_coordinator.active
            raise ConflictError(
                "Дождитесь завершения обработки сообщения в другом чате",
                {"dialog_id": str(active.dialog_id) if active else None},
            )
        try:
            await self._lock_turn_admission(session)
            database_active = await self._find_active_ai_turn(
                session, exclude_message_id=exclude_message_id
            )
            if database_active is not None:
                raise ConflictError(
                    "Дождитесь завершения обработки сообщения в другом чате",
                    {"dialog_id": str(database_active[0])},
                )
        except Exception:
            self._turn_coordinator.release(dialog_id, message_id)
            raise

    @staticmethod
    async def _lock_turn_admission(session: AsyncSession) -> None:
        bind = session.bind
        if bind is not None and bind.dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": AI_TURN_ADMISSION_LOCK_KEY},
            )

    @staticmethod
    async def _find_active_ai_turn(
        session: AsyncSession,
        *,
        exclude_message_id: uuid.UUID | None = None,
        include_pending: bool = True,
    ) -> tuple[uuid.UUID, uuid.UUID] | None:
        statuses = [MessageProcessingStatus.PROCESSING]
        if include_pending:
            statuses.insert(0, MessageProcessingStatus.PENDING)
        statement = (
            select(Message.dialog_id, Message.id)
            .join(Dialog, Message.dialog_id == Dialog.id)
            .where(
                Dialog.status == DialogStatus.ACTIVE,
                Dialog.mode == DialogMode.AI_SUPPORT,
                Message.author_type == MessageAuthor.USER,
                Message.processing_status.in_(statuses),
            )
            .order_by(Message.created_at, Message.id)
            .limit(1)
        )
        if exclude_message_id is not None:
            statement = statement.where(Message.id != exclude_message_id)
        row = (await session.execute(statement)).first()
        return (row[0], row[1]) if row is not None else None

    async def _escalate(
        self,
        dialog_id: uuid.UUID,
        confidence: float,
        sources: list[dict[str, object]],
        started: float,
        runtime_settings: RuntimeSettings,
        prompt_content: str,
        trigger_message_id: uuid.UUID,
        usage: ProviderUsage | None,
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
            usage,
            runtime_settings,
            prompt_content,
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

    async def _low_confidence_streak(
        self,
        dialog_id: uuid.UUID,
        message_id: uuid.UUID,
        threshold: float,
    ) -> int:
        async with self._session_factory() as session:
            trigger = await session.get(Message, message_id)
            if trigger is None:
                return 0
            user_messages = list(
                await session.scalars(
                    select(Message)
                    .where(
                        Message.dialog_id == dialog_id,
                        Message.author_type == MessageAuthor.USER,
                        or_(
                            Message.created_at < trigger.created_at,
                            and_(
                                Message.created_at == trigger.created_at,
                                Message.id <= trigger.id,
                            ),
                        ),
                    )
                    .order_by(Message.created_at, Message.id)
                )
            )
            return self._count_low_confidence_streak(
                [message.confidence for message in user_messages], threshold
            )

    @staticmethod
    def _count_low_confidence_streak(
        confidences: list[float | None], threshold: float
    ) -> int:
        streak = 0
        for confidence in reversed(confidences):
            if confidence is None or confidence >= threshold:
                break
            streak += 1
        return streak

    @staticmethod
    def _combine_usage(*usages: ProviderUsage | None) -> ProviderUsage | None:
        if not any(usage is not None for usage in usages):
            return None

        def total(field: str) -> int | None:
            values = [
                value
                for usage in usages
                if usage is not None
                for value in [getattr(usage, field)]
                if value is not None
            ]
            return sum(values) if values else None

        return ProviderUsage(
            prompt_tokens=total("prompt_tokens"),
            completion_tokens=total("completion_tokens"),
            precached_prompt_tokens=total("precached_prompt_tokens"),
        )

    @staticmethod
    def _explicit_operator_request(text: str) -> bool:
        normalized = " ".join(text.casefold().split())
        direct_request = normalized in {
            "оператор",
            "специалист",
            "живой человек",
            "человек",
        }
        has_negation = any(
            marker in normalized for marker in _OPERATOR_REQUEST_NEGATIONS
        )
        positive_text = normalized
        for marker in _OPERATOR_REQUEST_NEGATIONS:
            positive_text = positive_text.replace(marker, " ")
        marker_request = any(
            marker in positive_text for marker in _OPERATOR_REQUEST_MARKERS
        )
        return (direct_request or marker_request) and (
            marker_request or not has_negation
        )

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

    async def _mark_turn_pending(self, message_id: uuid.UUID) -> None:
        try:
            async with self._session_factory() as session:
                trigger = await session.get(Message, message_id, with_for_update=True)
                if (
                    trigger is None
                    or trigger.author_type != MessageAuthor.USER
                    or trigger.processing_status != MessageProcessingStatus.PROCESSING
                ):
                    return
                trigger.processing_status = MessageProcessingStatus.PENDING
                trigger.processing_error = None
                await session.commit()
        except Exception:
            logger.exception("Unable to requeue cancelled turn %s", message_id)

    async def _record_metric(
        self,
        dialog_id: uuid.UUID,
        started: float,
        confidence: float | None,
        escalated: bool,
        usage: ProviderUsage | None,
        runtime_settings: RuntimeSettings | None,
        prompt_content: str | None,
        *,
        event_type: str = "user_turn",
        success: bool = True,
        error_message: str | None = None,
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
                        system_prompt=prompt_content,
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
        except Exception:
            logger.exception(
                "Unable to persist %s metric for dialog %s", event_type, dialog_id
            )

    @staticmethod
    async def _turn_completed(
        session: AsyncSession,
        trigger: Message,
    ) -> bool:
        if trigger.processing_status in {
            MessageProcessingStatus.COMPLETED,
            MessageProcessingStatus.FAILED,
        }:
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
        return assistant_id is not None

    async def _processing_state(
        self, session: AsyncSession, dialog: Dialog
    ) -> tuple[bool, str | None]:
        if dialog.status != DialogStatus.ACTIVE:
            return False, None
        if dialog.mode == DialogMode.OPERATOR_SUPPORT:
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
        if await self._turn_completed(session, trigger):
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
            .where(Message.author_type != MessageAuthor.SYSTEM)
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
                .where(Message.author_type != MessageAuthor.SYSTEM)
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
