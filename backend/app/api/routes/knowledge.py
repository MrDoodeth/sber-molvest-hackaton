from __future__ import annotations

import uuid
from pathlib import PurePath
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response

from app.api.deps import get_container, get_request_actor
from app.api.openapi import API_RESPONSES
from app.contracts.schemas import (
    KnowledgeDocumentDto,
    KnowledgeDocumentPatch,
    KnowledgeDocumentsResponse,
    KnowledgeSectionCreate,
    KnowledgeSectionDto,
    KnowledgeSectionPatch,
)
from app.core.constants import DEFAULT_CASE_SECTION_ID, DOCUMENTATION_SECTION_ID
from app.core.enums import DocumentSourceType, UserRole
from app.core.errors import ForbiddenError, UnprocessableError
from app.models import User
from app.services.attachments import validate_upload
from app.services.container import ApplicationContainer

router = APIRouter(
    prefix="/admin/knowledge",
    tags=["Knowledge"],
    responses=API_RESPONSES,
)


def require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Endpoint доступен только администратору")


@router.get("/sections", response_model=list[KnowledgeSectionDto])
async def sections(
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> list[KnowledgeSectionDto]:
    require_admin(user)
    return await container.knowledge_base.list_sections()


@router.post("/sections", response_model=KnowledgeSectionDto, status_code=201)
async def create_section(
    payload: KnowledgeSectionCreate,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeSectionDto:
    require_admin(user)
    return await container.knowledge_base.create_section(payload.name)


@router.patch("/sections/{section_id}", response_model=KnowledgeSectionDto)
async def patch_section(
    section_id: uuid.UUID,
    payload: KnowledgeSectionPatch,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeSectionDto:
    require_admin(user)
    return await container.knowledge_base.patch_section(section_id, payload)


@router.delete("/sections/{section_id}", status_code=204, response_model=None)
async def delete_section(
    section_id: uuid.UUID,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> None:
    require_admin(user)
    await container.knowledge_base.delete_section(section_id)


@router.get("/documents", response_model=KnowledgeDocumentsResponse)
async def documents(
    section_id: uuid.UUID | None = None,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentsResponse:
    require_admin(user)
    return KnowledgeDocumentsResponse(
        items=await container.knowledge_base.list_documents(section_id)
    )


@router.post(
    "/sections/{section_id}/documents",
    response_model=KnowledgeDocumentDto,
    status_code=201,
)
async def upload_document(
    section_id: uuid.UUID,
    file: UploadFile = File(description="PDF, DOCX, HTML or Markdown; maximum 40 MB."),
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentDto:
    require_admin(user)
    if section_id == DEFAULT_CASE_SECTION_ID:
        raise UnprocessableError(
            "Раздел «Журнал обращений» заполняется только одобренными кейсами"
        )
    data = await file.read(container.settings.permanent_document_max_bytes + 1)
    upload = validate_upload(
        file_name=file.filename,
        content_type=file.content_type,
        data=data,
        permanent=True,
        settings=container.settings,
    )
    document_title = PurePath(upload.file_name).stem.strip()
    if not document_title:
        raise UnprocessableError("Название документа обязательно")
    source_type = (
        DocumentSourceType.OFFICIAL_1C_DOCS
        if section_id == DOCUMENTATION_SECTION_ID
        else DocumentSourceType.INTERNAL_KB
    )
    return await container.knowledge_base.create_document(
        upload=upload,
        section_id=section_id,
        source_type=source_type,
        title=document_title,
        one_c_version=None,
        tags=[],
    )


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentDto)
async def document(
    document_id: uuid.UUID,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentDto:
    require_admin(user)
    return await container.knowledge_base.get_document(document_id)


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> Response:
    require_admin(user)
    data, media_type, file_name = await container.knowledge_base.read_document(
        document_id
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": (f"attachment; filename*=UTF-8''{quote(file_name)}")
        },
    )


@router.patch("/documents/{document_id}", response_model=KnowledgeDocumentDto)
async def patch_document(
    document_id: uuid.UUID,
    payload: KnowledgeDocumentPatch,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentDto:
    require_admin(user)
    return await container.knowledge_base.patch_document(document_id, payload)


@router.post("/documents/{document_id}/reindex", response_model=KnowledgeDocumentDto)
async def reindex_document(
    document_id: uuid.UUID,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentDto:
    require_admin(user)
    return await container.knowledge_base.request_reindex(document_id)


@router.delete("/documents/{document_id}", status_code=204, response_model=None)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> None:
    require_admin(user)
    await container.knowledge_base.delete_document(document_id)
