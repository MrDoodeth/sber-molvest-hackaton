from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.enums import (
    CandidateSource,
    CandidateStatus,
    DialogChannel,
    DialogMode,
    DialogStatus,
    DocumentSourceType,
    FeedbackVerdict,
    IndexStatus,
    MessageAuthor,
    PromptType,
    StrEnum,
    UserRole,
)

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    return datetime.now(UTC)


def enum_type(enum: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
        create_constraint=True,
    )


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON_TYPE, list[Any]: JSON_TYPE}


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class User(UUIDPrimaryKey, Base):
    __tablename__ = "users"

    role: Mapped[UserRole] = mapped_column(enum_type(UserRole, "user_role"), index=True)
    display_name: Mapped[str] = mapped_column(String(200))


class Dialog(UUIDPrimaryKey, Base):
    __tablename__ = "dialogs"
    __table_args__ = (
        CheckConstraint(
            "dialog_confidence >= 0 AND dialog_confidence <= 1",
            name="ck_dialog_confidence_range",
        ),
        CheckConstraint(
            "(status = 'active' AND closed_at IS NULL) OR "
            "(status = 'closed' AND closed_at IS NOT NULL)",
            name="ck_dialog_closed_at_matches_status",
        ),
        Index("ix_dialog_user_updated", "user_id", "updated_at"),
        Index("ix_dialog_operator_queue", "status", "mode", "assigned_operator_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[DialogStatus] = mapped_column(
        enum_type(DialogStatus, "dialog_status"), default=DialogStatus.ACTIVE
    )
    mode: Mapped[DialogMode] = mapped_column(
        enum_type(DialogMode, "dialog_mode"), default=DialogMode.AI_SUPPORT
    )
    channel: Mapped[DialogChannel] = mapped_column(
        enum_type(DialogChannel, "dialog_channel"), default=DialogChannel.WEB
    )
    dialog_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    assigned_operator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    assigned_operator: Mapped[User | None] = relationship(
        foreign_keys=[assigned_operator_id]
    )


class DialogFeedback(UUIDPrimaryKey, Base):
    __tablename__ = "dialog_feedback"
    __table_args__ = (UniqueConstraint("dialog_id", name="uq_feedback_dialog"),)

    dialog_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dialogs.id", ondelete="CASCADE"), index=True
    )
    verdict: Mapped[FeedbackVerdict] = mapped_column(
        enum_type(FeedbackVerdict, "feedback_verdict")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class Message(UUIDPrimaryKey, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "dialog_id", "client_message_id", name="uq_message_dialog_client_id"
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_message_confidence_range",
        ),
        CheckConstraint(
            "processing_status IS NULL OR processing_status IN "
            "('pending', 'processing', 'completed', 'failed')",
            name="ck_message_processing_status",
        ),
        Index("ix_message_dialog_created", "dialog_id", "created_at", "id"),
    )

    dialog_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dialogs.id", ondelete="CASCADE"), index=True
    )
    client_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    author_type: Mapped[MessageAuthor] = mapped_column(
        enum_type(MessageAuthor, "message_author")
    )
    text: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_TYPE, default=list, server_default=sql_text("'[]'")
    )
    processing_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class Attachment(UUIDPrimaryKey, Base):
    __tablename__ = "attachments"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    mime_type: Mapped[str] = mapped_column(String(255))
    gigachat_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OperatorDraft(UUIDPrimaryKey, Base):
    __tablename__ = "operator_drafts"
    __table_args__ = (
        UniqueConstraint("trigger_message_id", name="uq_draft_trigger_message"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_draft_confidence_range",
        ),
    )

    dialog_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dialogs.id", ondelete="CASCADE"), index=True
    )
    trigger_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_TYPE, default=list, server_default=sql_text("'[]'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class KnowledgeSection(UUIDPrimaryKey, Base):
    __tablename__ = "knowledge_sections"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class KnowledgeDocument(UUIDPrimaryKey, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index("ix_document_section_status", "section_id", "index_status"),
    )

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_sections.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[DocumentSourceType] = mapped_column(
        enum_type(DocumentSourceType, "document_source_type")
    )
    title: Mapped[str] = mapped_column(String(500))
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    one_c_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        JSON_TYPE, default=list, server_default=sql_text("'[]'")
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    index_status: Mapped[IndexStatus] = mapped_column(
        enum_type(IndexStatus, "document_index_status"), default=IndexStatus.UPLOADED
    )
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    section: Mapped[KnowledgeSection] = relationship()


class Chunk(UUIDPrimaryKey, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("vector_id", name="uq_chunk_vector_id"),
        Index("ix_chunk_doc", "doc_id"),
    )

    doc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text)
    vector_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_TYPE, default=dict
    )


class KnowledgeCandidate(UUIDPrimaryKey, Base):
    __tablename__ = "knowledge_candidates"
    __table_args__ = (UniqueConstraint("dialog_id", name="uq_candidate_dialog"),)

    dialog_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dialogs.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[CandidateSource] = mapped_column(
        enum_type(CandidateSource, "candidate_source")
    )
    generated_card: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    status: Mapped[CandidateStatus] = mapped_column(
        enum_type(CandidateStatus, "candidate_status"), default=CandidateStatus.PENDING
    )
    resulting_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class SystemPrompt(UUIDPrimaryKey, Base):
    __tablename__ = "system_prompts"
    __table_args__ = (
        UniqueConstraint("type", "version", name="uq_prompt_type_version"),
        CheckConstraint("version >= 1", name="ck_prompt_version_positive"),
        Index(
            "uq_prompt_active_type",
            "type",
            unique=True,
            postgresql_where=sql_text("is_active"),
            sqlite_where=sql_text("is_active = 1"),
        ),
    )

    type: Mapped[PromptType] = mapped_column(enum_type(PromptType, "prompt_type"))
    content: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON_TYPE)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )


class MetricEvent(UUIDPrimaryKey, Base):
    __tablename__ = "metric_events"
    __table_args__ = (
        CheckConstraint("latency_ms >= 0", name="ck_metric_latency_nonnegative"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_metric_confidence_range",
        ),
        CheckConstraint(
            "prompt_tokens IS NULL OR prompt_tokens >= 0",
            name="ck_metric_prompt_tokens_nonnegative",
        ),
        CheckConstraint(
            "completion_tokens IS NULL OR completion_tokens >= 0",
            name="ck_metric_completion_tokens_nonnegative",
        ),
        CheckConstraint(
            "precached_prompt_tokens IS NULL OR precached_prompt_tokens >= 0",
            name="ck_metric_precached_tokens_nonnegative",
        ),
        CheckConstraint(
            "system_prompt_version IS NULL OR system_prompt_version >= 1",
            name="ck_metric_prompt_version_positive",
        ),
        CheckConstraint(
            "rag_top_k IS NULL OR rag_top_k >= 1",
            name="ck_metric_rag_top_k_positive",
        ),
        CheckConstraint(
            "operator_escalation_threshold IS NULL OR "
            "(operator_escalation_threshold >= 0 AND "
            "operator_escalation_threshold <= 1)",
            name="ck_metric_threshold_range",
        ),
        Index("ix_metric_created", "created_at"),
    )

    dialog_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dialogs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    latency_ms: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precached_prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gigachat_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    system_prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rag_top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operator_escalation_threshold: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
