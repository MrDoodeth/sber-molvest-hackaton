from __future__ import annotations

import json
import uuid
from pathlib import PurePath
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_container, get_current_user
from app.api.openapi import PROTECTED_RESPONSES
from app.contracts.schemas import (
    KnowledgeDocumentDto,
    KnowledgeDocumentPatch,
    KnowledgeDocumentsResponse,
    KnowledgeSectionCreate,
    KnowledgeSectionDto,
    KnowledgeSectionPatch,
)
from app.core.enums import DocumentSourceType, IndexStatus, UserRole
from app.core.errors import ForbiddenError, UnprocessableError
from app.models import User
from app.services.attachments import validate_upload
from app.services.container import ApplicationContainer

router = APIRouter(
    prefix="/admin/knowledge",
    tags=["Knowledge"],
    responses=PROTECTED_RESPONSES,
)


def require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Endpoint доступен только администратору")


@router.get("/sections", response_model=list[KnowledgeSectionDto])
async def sections(
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> list[KnowledgeSectionDto]:
    require_admin(user)
    return await container.knowledge_base.list_sections()


@router.post("/sections", response_model=KnowledgeSectionDto, status_code=201)
async def create_section(
    payload: KnowledgeSectionCreate,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeSectionDto:
    require_admin(user)
    return await container.knowledge_base.create_section(payload.name)


@router.patch("/sections/{section_id}", response_model=KnowledgeSectionDto)
async def patch_section(
    section_id: uuid.UUID,
    payload: KnowledgeSectionPatch,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeSectionDto:
    require_admin(user)
    return await container.knowledge_base.patch_section(section_id, payload)


@router.delete("/sections/{section_id}", status_code=204, response_model=None)
async def delete_section(
    section_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> None:
    require_admin(user)
    await container.knowledge_base.delete_section(section_id)


@router.get("/documents", response_model=KnowledgeDocumentsResponse)
async def documents(
    section_id: uuid.UUID | None = None,
    status: IndexStatus | None = None,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentsResponse:
    require_admin(user)
    return KnowledgeDocumentsResponse(
        items=await container.knowledge_base.list_documents(section_id, status)
    )


@router.post("/documents", response_model=KnowledgeDocumentDto, status_code=201)
async def upload_document(
    file: UploadFile = File(description="PDF, DOCX, HTML or Markdown; maximum 40 MB."),
    section_id: uuid.UUID = Form(description="Target knowledge section UUID."),
    source_type: Literal["official_1c_docs", "internal_kb"] = Form(
        description="official_1c_docs or internal_kb for direct uploads."
    ),
    title: str | None = Form(
        default=None,
        description="Optional display title; filename stem is used by default.",
    ),
    one_c_version: str | None = Form(
        default=None,
        description="Optional 1C configuration/version metadata.",
    ),
    tags: str = Form(
        default="[]",
        description='JSON-encoded string array, for example `["бухгалтерия"]`.',
    ),
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentDto:
    require_admin(user)
    data = await file.read(container.settings.permanent_document_max_bytes + 1)
    upload = validate_upload(
        file_name=file.filename,
        content_type=file.content_type,
        data=data,
        permanent=True,
        settings=container.settings,
    )
    try:
        parsed_tags = json.loads(tags)
    except json.JSONDecodeError as exc:
        raise UnprocessableError("tags должен быть JSON-массивом строк") from exc
    if not isinstance(parsed_tags, list) or not all(
        isinstance(item, str) for item in parsed_tags
    ):
        raise UnprocessableError("tags должен быть JSON-массивом строк")
    document_title = (title or PurePath(upload.file_name).stem).strip()
    if not document_title:
        raise UnprocessableError("Название документа обязательно")
    return await container.knowledge_base.create_document(
        upload=upload,
        section_id=section_id,
        source_type=DocumentSourceType(source_type),
        title=document_title,
        one_c_version=one_c_version,
        tags=[item.strip() for item in parsed_tags if item.strip()],
    )


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentDto)
async def document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentDto:
    require_admin(user)
    return await container.knowledge_base.get_document(document_id)


@router.patch("/documents/{document_id}", response_model=KnowledgeDocumentDto)
async def patch_document(
    document_id: uuid.UUID,
    payload: KnowledgeDocumentPatch,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentDto:
    require_admin(user)
    return await container.knowledge_base.patch_document(document_id, payload)


@router.post("/documents/{document_id}/reindex", response_model=KnowledgeDocumentDto)
async def reindex_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentDto:
    require_admin(user)
    return await container.knowledge_base.request_reindex(document_id)


@router.delete("/documents/{document_id}", status_code=204, response_model=None)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> None:
    require_admin(user)
    await container.knowledge_base.delete_document(document_id)
