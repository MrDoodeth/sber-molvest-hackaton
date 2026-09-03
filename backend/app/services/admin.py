from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.mappers import (
    candidate_dto,
    dialog_detail,
    dialog_summary,
    feedback_dto,
    message_dto,
)
from app.contracts.schemas import (
    AdminDialogAudit,
    AdminDialogDetail,
    AdminDialogListItem,
    AdminDialogPage,
    MonitoringResponse,
)
from app.core.enums import (
    CandidateStatus,
    DialogMode,
    DialogStatus,
    FeedbackVerdict,
    MessageAuthor,
    MonitoringPeriod,
    UserRole,
)
from app.core.errors import ForbiddenError, NotFoundError
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
from app.services.settings import PromptService, SettingsService


class AdminService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings_service: SettingsService,
        prompt_service: PromptService,
    ) -> None:
        self._session_factory = session_factory
        self._settings_service = settings_service
        self._prompt_service = prompt_service

    async def list_dialogs(
        self,
        *,
        admin: User,
        feedback: str,
        page: int,
        page_size: int,
        date_from: datetime | None,
        date_to: datetime | None,
        resolved_by: str | None,
        has_attachment: bool | None,
        moderation: str | None,
    ) -> AdminDialogPage:
        self._require_admin(admin)
        async with self._session_factory() as session:
            filters = [Dialog.status == DialogStatus.CLOSED]
            if feedback == "unrated":
                filters.append(
                    ~exists(
                        select(DialogFeedback.id).where(
                            DialogFeedback.dialog_id == Dialog.id
                        )
                    )
                )
            else:
                filters.append(
                    exists(
                        select(DialogFeedback.id).where(
                            DialogFeedback.dialog_id == Dialog.id,
                            DialogFeedback.verdict == FeedbackVerdict(feedback),
                        )
                    )
                )
            candidate_exists = exists(
                select(KnowledgeCandidate.id).where(
                    KnowledgeCandidate.dialog_id == Dialog.id
                )
            )
            if moderation == "unmoderated":
                filters.append(
                    or_(
                        ~candidate_exists,
                        exists(
                            select(KnowledgeCandidate.id).where(
                                KnowledgeCandidate.dialog_id == Dialog.id,
                                KnowledgeCandidate.status == CandidateStatus.PENDING,
                            )
                        ),
                    )
                )
            elif moderation == "moderated":
                filters.append(
                    exists(
                        select(KnowledgeCandidate.id).where(
                            KnowledgeCandidate.dialog_id == Dialog.id,
                            KnowledgeCandidate.status.in_(
                                [
                                    CandidateStatus.APPROVED,
                                    CandidateStatus.REJECTED,
                                ]
                            ),
                        )
                    )
                )
            if date_from is not None:
                filters.append(Dialog.closed_at >= date_from)
            if date_to is not None:
                filters.append(Dialog.closed_at < date_to)
            if resolved_by == "ai":
                filters.append(Dialog.mode == DialogMode.AI_SUPPORT)
            elif resolved_by == "operator":
                filters.append(Dialog.mode == DialogMode.OPERATOR_SUPPORT)
            attachment_exists = exists(
                select(Attachment.id)
                .join(Message, Attachment.message_id == Message.id)
                .where(Message.dialog_id == Dialog.id)
            )
            if has_attachment is True:
                filters.append(attachment_exists)
            elif has_attachment is False:
                filters.append(~attachment_exists)

            total = int(
                await session.scalar(select(func.count(Dialog.id)).where(*filters)) or 0
            )
            dialogs = list(
                await session.scalars(
                    select(Dialog)
                    .where(*filters)
                    .order_by(Dialog.closed_at.desc(), Dialog.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            items: list[AdminDialogListItem] = []
            for dialog in dialogs:
                owner = await session.get(User, dialog.user_id)
                if owner is None:
                    continue
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
                feedback_row = await session.scalar(
                    select(DialogFeedback).where(DialogFeedback.dialog_id == dialog.id)
                )
                candidate = await session.scalar(
                    select(KnowledgeCandidate).where(
                        KnowledgeCandidate.dialog_id == dialog.id
                    )
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
                attachment_present = (
                    await session.scalar(
                        select(Attachment.id)
                        .join(Message, Attachment.message_id == Message.id)
                        .where(Message.dialog_id == dialog.id)
                        .limit(1)
                    )
                    is not None
                )
                summary = dialog_summary(
                    dialog,
                    last,
                    operator,
                    owner=owner,
                    first_user_message=first_user_message,
                    has_attachment=attachment_present,
                    feedback=feedback_row,
                    candidate=candidate,
                )
                items.append(
                    AdminDialogListItem(
                        **summary.model_dump(),
                        resolved_by=(
                            "operator"
                            if dialog.mode == DialogMode.OPERATOR_SUPPORT
                            else "ai"
                        ),
                        last_confidence=dialog.dialog_confidence,
                        moderation_status=(
                            candidate.status.value
                            if candidate is not None
                            and candidate.status
                            in {CandidateStatus.APPROVED, CandidateStatus.REJECTED}
                            else "unmoderated"
                        ),
                    )
                )
            return AdminDialogPage(
                items=items,
                page=page,
                page_size=page_size,
                total=total,
                total_pages=math.ceil(total / page_size) if total else 0,
            )

    async def dialog_detail(
        self, admin: User, dialog_id: uuid.UUID
    ) -> AdminDialogDetail:
        self._require_admin(admin)
        async with self._session_factory() as session:
            dialog = await session.get(Dialog, dialog_id)
            if dialog is None:
                raise NotFoundError("Диалог не найден")
            owner = await session.get(User, dialog.user_id)
            if owner is None:
                raise NotFoundError("Владелец диалога не найден")
            operator = (
                await session.get(User, dialog.assigned_operator_id)
                if dialog.assigned_operator_id
                else None
            )
            messages = list(
                await session.scalars(
                    select(Message)
                    .where(Message.dialog_id == dialog_id)
                    .order_by(Message.created_at, Message.id)
                )
            )
            attachments = list(
                await session.scalars(
                    select(Attachment)
                    .join(Message, Attachment.message_id == Message.id)
                    .where(Message.dialog_id == dialog_id)
                )
            )
            attachments_by_message: dict[uuid.UUID, list[Attachment]] = {}
            for attachment in attachments:
                attachments_by_message.setdefault(attachment.message_id, []).append(
                    attachment
                )
            feedback = await session.scalar(
                select(DialogFeedback).where(DialogFeedback.dialog_id == dialog_id)
            )
            candidate = await session.scalar(
                select(KnowledgeCandidate).where(
                    KnowledgeCandidate.dialog_id == dialog_id
                )
            )
            reviewer = (
                await session.get(User, candidate.reviewed_by)
                if candidate and candidate.reviewed_by
                else None
            )
            resulting_document = (
                await session.get(KnowledgeDocument, candidate.resulting_document_id)
                if candidate and candidate.resulting_document_id
                else None
            )
            resulting_section = (
                await session.get(KnowledgeSection, resulting_document.section_id)
                if resulting_document is not None
                else None
            )
            first_user_message = next(
                (
                    message
                    for message in messages
                    if message.author_type == MessageAuthor.USER
                ),
                None,
            )
            resolution_event_types = (
                ("operator_template", "user_turn")
                if dialog.mode == DialogMode.OPERATOR_SUPPORT
                else ("user_turn",)
            )
            latest_metric = await session.scalar(
                select(MetricEvent)
                .where(
                    MetricEvent.dialog_id == dialog_id,
                    MetricEvent.event_type.in_(resolution_event_types),
                )
                .order_by(MetricEvent.created_at.desc(), MetricEvent.id.desc())
                .limit(1)
            )
            first_turn_metric = await session.scalar(
                select(MetricEvent)
                .where(
                    MetricEvent.dialog_id == dialog_id,
                    MetricEvent.event_type == "user_turn",
                )
                .order_by(MetricEvent.created_at, MetricEvent.id)
                .limit(1)
            )
            escalation_metric = await session.scalar(
                select(MetricEvent)
                .where(
                    MetricEvent.dialog_id == dialog_id,
                    MetricEvent.event_type == "user_turn",
                    MetricEvent.escalated.is_(True),
                )
                .order_by(MetricEvent.created_at.desc(), MetricEvent.id.desc())
                .limit(1)
            )
            last = messages[-1] if messages else None
            return AdminDialogDetail(
                dialog=dialog_detail(
                    dialog,
                    owner,
                    last,
                    operator,
                    first_user_message=first_user_message,
                    has_attachment=bool(attachments),
                    feedback=feedback,
                    candidate=candidate,
                ),
                messages=[
                    message_dto(
                        message,
                        attachments_by_message.get(message.id, []),
                        operator
                        if message.author_type == MessageAuthor.OPERATOR
                        else None,
                    )
                    for message in messages
                ],
                feedback=feedback_dto(feedback) if feedback else None,
                candidate=(
                    candidate_dto(
                        candidate,
                        reviewer,
                        resulting_document,
                        resulting_section,
                    )
                    if candidate
                    else None
                ),
                audit=AdminDialogAudit(
                    resolved_by=(
                        "operator"
                        if dialog.mode == DialogMode.OPERATOR_SUPPORT
                        else "ai"
                    ),
                    gigachat_model=(
                        latest_metric.gigachat_model if latest_metric else None
                    ),
                    system_prompt=(
                        first_turn_metric.system_prompt
                        if first_turn_metric
                        else latest_metric.system_prompt
                        if latest_metric
                        else None
                    ),
                    escalation_threshold=(
                        escalation_metric.operator_escalation_threshold
                        if escalation_metric
                        else None
                    ),
                ),
            )

    async def monitoring(
        self, admin: User, period: MonitoringPeriod
    ) -> MonitoringResponse:
        self._require_admin(admin)
        start = self._period_start(period)
        async with self._session_factory() as session:
            metric_statement = select(MetricEvent).where(
                MetricEvent.event_type == "user_turn"
            )
            if start is not None:
                metric_statement = metric_statement.where(
                    MetricEvent.created_at >= start
                )
            metrics = list(await session.scalars(metric_statement))
            feedback_statement = select(DialogFeedback)
            if start is not None:
                feedback_statement = feedback_statement.where(
                    DialogFeedback.created_at >= start
                )
            feedback_rows = list(await session.scalars(feedback_statement))
            total = len(metrics)
            escalations = sum(1 for metric in metrics if metric.escalated)
            failed = sum(1 for metric in metrics if not metric.success)
            resolved_by_ai = sum(
                1 for metric in metrics if metric.success and not metric.escalated
            )
        average_latency = (
            sum(metric.latency_ms for metric in metrics) / total if total else 0.0
        )
        helpful = sum(
            1
            for feedback in feedback_rows
            if feedback.verdict == FeedbackVerdict.HELPFUL
        )
        return MonitoringResponse(
            total_requests=total,
            ai_resolved=resolved_by_ai,
            ai_resolved_rate=self._percent(resolved_by_ai, total) / 100,
            escalations=escalations,
            escalation_rate=self._percent(escalations, total) / 100,
            failed_requests=failed,
            average_response_time_ms=round(average_latency, 2),
            helpful=helpful,
            helpful_rate=self._percent(helpful, len(feedback_rows)) / 100,
        )

    @staticmethod
    def _period_start(period: MonitoringPeriod) -> datetime | None:
        now = datetime.now(UTC)
        if period == MonitoringPeriod.TODAY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == MonitoringPeriod.DAYS_7:
            return now - timedelta(days=7)
        if period == MonitoringPeriod.DAYS_30:
            return now - timedelta(days=30)
        return None

    @staticmethod
    def _percent(value: int, total: int) -> float:
        return round(value * 100 / total, 2) if total else 0.0

    @staticmethod
    def _require_admin(user: User) -> None:
        if user.role != UserRole.ADMIN:
            raise ForbiddenError("Endpoint доступен только администратору")
