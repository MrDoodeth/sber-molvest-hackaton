from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import (
    CandidateSource,
    CandidateStatus,
    DialogChannel,
    DialogMode,
    DialogStatus,
    FeedbackVerdict,
    IndexStatus,
    MessageAuthor,
    PromptType,
    UserRole,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class ErrorResponse(ApiModel):
    code: str
    message: str
    details: Any | None = None


class UserRef(ApiModel):
    id: uuid.UUID
    display_name: str


class CurrentUser(UserRef):
    role: UserRole


class DemoLoginRequest(ApiModel):
    role: UserRole


class SourceRef(ApiModel):
    document_id: uuid.UUID
    title: str
    label: str
    page: int | None = None
    heading_path: list[str] = Field(default_factory=list)


class AttachmentDto(ApiModel):
    id: uuid.UUID
    message_id: uuid.UUID
    file_name: str
    mime_type: str
    url: str
    size_bytes: int | None = None


class MessageDto(ApiModel):
    id: uuid.UUID
    dialog_id: uuid.UUID
    author_type: MessageAuthor
    author: UserRef | None = None
    text: str
    confidence: float | None = None
    attachments: list[AttachmentDto] = Field(default_factory=list)
    created_at: datetime


class MessagePage(ApiModel):
    items: list[MessageDto]
    next_cursor: uuid.UUID | None = None


class FeedbackRequest(ApiModel):
    verdict: FeedbackVerdict


class FeedbackDto(ApiModel):
    id: uuid.UUID
    dialog_id: uuid.UUID
    verdict: FeedbackVerdict
    created_at: datetime


class CandidateRef(ApiModel):
    id: uuid.UUID
    status: CandidateStatus
    source: CandidateSource


class OperatorTemplateDto(ApiModel):
    dialog_id: uuid.UUID
    dialog_updated_at: datetime
    text: str
    created_at: datetime


class DialogSummary(ApiModel):
    id: uuid.UUID
    status: DialogStatus
    mode: DialogMode
    confidence: float
    is_processing: bool = False
    processing_error: str | None = None
    assigned_operator: UserRef | None = None
    last_message_preview: str | None = None
    last_message_author: MessageAuthor | None = None
    title: str | None = None
    user: UserRef | None = None
    has_attachment: bool = False
    escalated_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime
    feedback: FeedbackDto | None = None
    candidate: CandidateRef | None = None


class DialogDetail(DialogSummary):
    user: UserRef
    channel: DialogChannel
    created_at: datetime


class KnowledgeSectionCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class KnowledgeSectionPatch(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class KnowledgeSectionDto(ApiModel):
    id: uuid.UUID
    name: str
    is_enabled: bool
    is_system: bool
    document_count: int = 0
    created_at: datetime


class KnowledgeDocumentPatch(ApiModel):
    is_enabled: bool | None = None


class KnowledgeDocumentDto(ApiModel):
    id: uuid.UUID
    section_id: uuid.UUID
    title: str
    is_enabled: bool
    index_status: IndexStatus
    index_error: str | None = None
    indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    download_url: str


class KnowledgeDocumentsResponse(ApiModel):
    items: list[KnowledgeDocumentDto]


class PromptDto(ApiModel):
    id: uuid.UUID
    type: PromptType
    content: str
    updated_at: datetime
    updated_by: UserRef | None = None


class PromptUpdate(ApiModel):
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt must not be blank")
        return value


class SettingsCapabilities(ApiModel):
    gigachat_context_limit: int
    embedding_context_limit: int


class ModelOptionDto(ApiModel):
    id: str
    label: str
    context_limit: int


class AdminSettingsResponse(ApiModel):
    active_model: str
    gigachat_context_ratio: float
    gigachat_max_output_tokens: int
    embedding_context_ratio: float
    rag_top_k: int
    operator_escalation_threshold: float
    capabilities: SettingsCapabilities
    available_models: list[ModelOptionDto]


class AdminSettingsUpdate(ApiModel):
    operator_escalation_threshold: float = Field(ge=0, le=1)


class CaseCard(ApiModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    problem: str = Field(min_length=1)
    result: str = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название кейса не может быть пустым")
        return value

    @field_validator("problem", "result")
    @classmethod
    def strip_card_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Поле карточки не может быть пустым")
        return value


class CandidatePatch(ApiModel):
    generated_card: CaseCard


class CandidateApproveRequest(ApiModel):
    generated_card: CaseCard | None = None


class KnowledgeCandidateDto(ApiModel):
    id: uuid.UUID
    dialog_id: uuid.UUID
    source: CandidateSource
    generated_card: CaseCard
    status: CandidateStatus
    resulting_document_id: uuid.UUID | None = None
    resulting_document: KnowledgeDocumentDto | None = None
    reviewed_by: UserRef | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class AdminDialogListItem(DialogSummary):
    resolved_by: Literal["ai", "operator"]
    last_confidence: float | None = None
    moderation_status: Literal["unmoderated", "approved", "rejected"]


class AdminDialogPage(ApiModel):
    items: list[AdminDialogListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class AdminDialogAudit(ApiModel):
    resolved_by: Literal["ai", "operator"]
    gigachat_model: str | None = None
    system_prompt: str | None = None
    escalation_threshold: float | None = None


class AdminDialogDetail(ApiModel):
    dialog: DialogDetail
    messages: list[MessageDto]
    feedback: FeedbackDto | None = None
    candidate: KnowledgeCandidateDto | None = None
    audit: AdminDialogAudit


class MonitoringResponse(ApiModel):
    total_requests: int
    ai_resolved: int
    ai_resolved_rate: float
    escalations: int
    escalation_rate: float
    failed_requests: int
    average_response_time_ms: float
    helpful: int
    helpful_rate: float
