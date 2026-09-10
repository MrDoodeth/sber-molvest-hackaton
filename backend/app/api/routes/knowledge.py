from __future__ import annotations

import re
import uuid
from pathlib import PurePath
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile
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
from app.services.attachments import ValidatedUpload, validate_upload_stream
from app.services.container import ApplicationContainer

router = APIRouter(
    prefix="/admin/knowledge",
    tags=["Knowledge"],
    responses=API_RESPONSES,
)

CASE_CARD_PATTERN = re.compile(
    r"\A#\s+([^\n]+)\n+##\s+Проблема\s*\n(.+?)\n+##\s+Результат\s*\n(.+?)\s*\Z",
    re.DOTALL,
)
CASE_CARD_MAX_BYTES = 2 * 1024 * 1024


def _case_card_title(upload: ValidatedUpload) -> str:
    if upload.size_bytes > CASE_CARD_MAX_BYTES:
        raise UnprocessableError(
            "Карточка решённого обращения должна быть не больше 2 МБ",
            {"max_bytes": CASE_CARD_MAX_BYTES},
        )
    upload.source.seek(0)
    try:
        content = upload.source.read().decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise UnprocessableError("Markdown-карточка должна быть в UTF-8") from exc
    finally:
        upload.source.seek(0)
    match = CASE_CARD_PATTERN.fullmatch(content)
    if match is None or not match.group(2).strip() or not match.group(3).strip():
        raise UnprocessableError(
            "Ожидается Markdown-карточка с заголовками #, ## Проблема и ## Результат"
        )
    title = match.group(1).strip()
    if len(title) > 500:
        raise UnprocessableError(
            "Заголовок карточки должен быть не длиннее 500 символов"
        )
    return title


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
    page: int = Query(default=1, ge=1),
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentsResponse:
    require_admin(user)
    page_size = 10
    items, total = await container.knowledge_base.list_documents(
        section_id, page, page_size
    )
    return KnowledgeDocumentsResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post(
    "/sections/{section_id}/documents",
    response_model=KnowledgeDocumentDto,
    status_code=201,
)
async def upload_document(
    section_id: uuid.UUID,
    file: UploadFile = File(
        description=(
            "PDF, DOCX, HTML or Markdown; maximum 40 MB. The case journal accepts "
            "only UTF-8 Markdown case cards up to 2 MB."
        )
    ),
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeDocumentDto:
    require_admin(user)
    upload = await validate_upload_stream(
        file_name=file.filename,
        content_type=file.content_type,
        upload=file,
        permanent=True,
        settings=container.settings,
    )
    if section_id == DEFAULT_CASE_SECTION_ID:
        if upload.extension not in {".md", ".markdown"}:
            raise UnprocessableError(
                "В Журнал обращений можно загружать только Markdown-карточки"
            )
        document_title = _case_card_title(upload)
    else:
        document_title = PurePath(upload.file_name).stem.strip()
    if not document_title:
        raise UnprocessableError("Название документа обязательно")
    if section_id == DEFAULT_CASE_SECTION_ID:
        source_type = DocumentSourceType.RESOLVED_CASE
    elif section_id == DOCUMENTATION_SECTION_ID:
        source_type = DocumentSourceType.OFFICIAL_1C_DOCS
    else:
        source_type = DocumentSourceType.INTERNAL_KB
    return await container.knowledge_base.create_document(
        upload=upload,
        section_id=section_id,
        source_type=source_type,
        title=document_title,
        one_c_version=None,
        tags=["resolved_case"] if section_id == DEFAULT_CASE_SECTION_ID else [],
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
