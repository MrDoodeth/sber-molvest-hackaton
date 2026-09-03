from __future__ import annotations

from pathlib import PurePosixPath

from app.contracts.schemas import (
    AttachmentDto,
    CandidateRef,
    CurrentUser,
    DialogDetail,
    DialogSummary,
    FeedbackDto,
    KnowledgeCandidateDto,
    KnowledgeDocumentDto,
    KnowledgeSectionDto,
    MessageDto,
    PromptDto,
    UserRef,
)
from app.core.constants import PROTECTED_SECTION_IDS
from app.models import (
    Attachment,
    Dialog,
    DialogFeedback,
    KnowledgeCandidate,
    KnowledgeDocument,
    KnowledgeSection,
    Message,
    SystemPrompt,
    User,
)


def user_ref(user: User) -> UserRef:
    return UserRef(id=user.id, display_name=user.display_name)


def current_user(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, display_name=user.display_name)


def attachment_dto(attachment: Attachment) -> AttachmentDto:
    return AttachmentDto(
        id=attachment.id,
        message_id=attachment.message_id,
        file_name=PurePosixPath(attachment.storage_key).name,
        mime_type=attachment.mime_type,
        url=f"/api/attachments/{attachment.id}",
        size_bytes=attachment.size_bytes,
    )


def message_dto(
    message: Message,
    attachments: list[Attachment] | None = None,
    author: User | None = None,
) -> MessageDto:
    return MessageDto(
        id=message.id,
        dialog_id=message.dialog_id,
        author_type=message.author_type,
        author=user_ref(author) if author else None,
        text=message.text,
        confidence=message.confidence,
        attachments=[attachment_dto(item) for item in attachments or []],
        created_at=message.created_at,
    )


def dialog_summary(
    dialog: Dialog,
    last_message: Message | None = None,
    operator: User | None = None,
    *,
    owner: User | None = None,
    first_user_message: Message | None = None,
    has_attachment: bool = False,
    is_processing: bool = False,
    processing_error: str | None = None,
    feedback: DialogFeedback | None = None,
    candidate: KnowledgeCandidate | None = None,
) -> DialogSummary:
    preview = None
    if last_message is not None:
        normalized = " ".join(last_message.text.split())
        preview = normalized[:160] or None
    return DialogSummary(
        id=dialog.id,
        status=dialog.status,
        mode=dialog.mode,
        confidence=dialog.dialog_confidence,
        is_processing=is_processing,
        processing_error=processing_error,
        assigned_operator=user_ref(operator) if operator else None,
        last_message_preview=preview,
        last_message_author=last_message.author_type if last_message else None,
        title=(
            " ".join(first_user_message.text.split())[:120] or None
            if first_user_message is not None
            else None
        ),
        user=user_ref(owner) if owner else None,
        has_attachment=has_attachment,
        escalated_at=dialog.escalated_at,
        closed_at=dialog.closed_at,
        created_at=dialog.created_at,
        updated_at=dialog.updated_at,
        feedback=feedback_dto(feedback) if feedback else None,
        candidate=candidate_ref(candidate) if candidate else None,
    )


def dialog_detail(
    dialog: Dialog,
    user: User,
    last_message: Message | None = None,
    operator: User | None = None,
    *,
    first_user_message: Message | None = None,
    has_attachment: bool = False,
    is_processing: bool = False,
    processing_error: str | None = None,
    feedback: DialogFeedback | None = None,
    candidate: KnowledgeCandidate | None = None,
) -> DialogDetail:
    summary = dialog_summary(
        dialog,
        last_message,
        operator,
        owner=user,
        first_user_message=first_user_message,
        has_attachment=has_attachment,
        is_processing=is_processing,
        processing_error=processing_error,
        feedback=feedback,
        candidate=candidate,
    )
    return DialogDetail(
        **summary.model_dump(),
        channel=dialog.channel,
    )


def feedback_dto(feedback: DialogFeedback) -> FeedbackDto:
    return FeedbackDto.model_validate(feedback)


def section_dto(
    section: KnowledgeSection, document_count: int = 0
) -> KnowledgeSectionDto:
    return KnowledgeSectionDto(
        id=section.id,
        name=section.name,
        is_enabled=section.is_enabled,
        is_system=section.id in PROTECTED_SECTION_IDS,
        document_count=document_count,
        created_at=section.created_at,
    )


def document_dto(
    document: KnowledgeDocument, section: KnowledgeSection
) -> KnowledgeDocumentDto:
    return KnowledgeDocumentDto(
        id=document.id,
        section_id=document.section_id,
        title=document.title,
        is_enabled=document.is_enabled,
        index_status=document.index_status,
        index_error=document.index_error,
        indexed_at=document.indexed_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
        download_url=f"/api/admin/knowledge/documents/{document.id}/download",
    )


def candidate_dto(
    candidate: KnowledgeCandidate,
    reviewer: User | None = None,
    resulting_document: KnowledgeDocument | None = None,
    resulting_section: KnowledgeSection | None = None,
) -> KnowledgeCandidateDto:
    return KnowledgeCandidateDto(
        id=candidate.id,
        dialog_id=candidate.dialog_id,
        source=candidate.source,
        generated_card=candidate.generated_card,
        status=candidate.status,
        resulting_document_id=candidate.resulting_document_id,
        resulting_document=(
            document_dto(resulting_document, resulting_section)
            if resulting_document is not None and resulting_section is not None
            else None
        ),
        reviewed_by=user_ref(reviewer) if reviewer else None,
        reviewed_at=candidate.reviewed_at,
        created_at=candidate.created_at,
    )


def candidate_ref(candidate: KnowledgeCandidate) -> CandidateRef:
    return CandidateRef(
        id=candidate.id,
        status=candidate.status,
        source=candidate.source,
    )


def prompt_dto(prompt: SystemPrompt, updater: User | None = None) -> PromptDto:
    return PromptDto(
        id=prompt.id,
        type=prompt.type,
        content=prompt.content,
        updated_at=prompt.updated_at,
        updated_by=user_ref(updater) if updater else None,
    )
