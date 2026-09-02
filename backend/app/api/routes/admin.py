from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Body, Depends, Query

from app.api.deps import get_container, get_current_user
from app.api.openapi import PROTECTED_RESPONSES
from app.contracts.schemas import (
    AdminDialogDetail,
    AdminDialogPage,
    AdminSettingsResponse,
    AdminSettingsUpdate,
    CandidateApproveRequest,
    CandidatePatch,
    KnowledgeCandidateDto,
    MonitoringResponse,
    PromptDto,
    PromptUpdate,
)
from app.core.enums import MonitoringPeriod, PromptType, UserRole
from app.core.errors import ForbiddenError
from app.models import User
from app.services.container import ApplicationContainer

router = APIRouter(prefix="/admin", responses=PROTECTED_RESPONSES)


def require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Endpoint доступен только администратору")


@router.get("/prompts", response_model=list[PromptDto], tags=["Prompts"])
async def prompts(
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> list[PromptDto]:
    require_admin(user)
    async with container.session_factory() as session:
        return await container.prompt_service.list_active(session)


@router.put("/prompts/{prompt_type}", response_model=PromptDto, tags=["Prompts"])
async def update_prompt(
    prompt_type: PromptType,
    payload: PromptUpdate,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> PromptDto:
    require_admin(user)
    async with container.session_factory() as session:
        return await container.prompt_service.create_version(
            session, prompt_type, payload.content, user.id
        )


@router.get("/settings", response_model=AdminSettingsResponse, tags=["Settings"])
async def settings(
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> AdminSettingsResponse:
    require_admin(user)
    async with container.session_factory() as session:
        return await container.settings_service.get_response(session)


@router.put("/settings", response_model=AdminSettingsResponse, tags=["Settings"])
async def update_settings(
    payload: AdminSettingsUpdate,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> AdminSettingsResponse:
    require_admin(user)
    async with container.session_factory() as session:
        return await container.settings_service.update(session, payload)


@router.get("/dialogs", response_model=AdminDialogPage, tags=["Admin Dialogs"])
async def admin_dialogs(
    feedback: Literal["helpful", "ai_error", "unrated"],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    closed_on: date | None = Query(
        default=None,
        alias="date",
        description="Frontend-compatible exact UTC closing date (YYYY-MM-DD).",
    ),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    resolved_by: Literal["ai", "operator"] | None = None,
    has_attachment: bool | None = None,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> AdminDialogPage:
    if closed_on is not None:
        date_from = datetime.combine(closed_on, time.min, tzinfo=UTC)
        date_to = date_from + timedelta(days=1)
    return await container.admin.list_dialogs(
        admin=user,
        feedback=feedback,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
        resolved_by=resolved_by,
        has_attachment=has_attachment,
    )


@router.get(
    "/dialogs/{dialog_id}",
    response_model=AdminDialogDetail,
    response_model_exclude_none=True,
    tags=["Admin Dialogs"],
)
async def admin_dialog_detail(
    dialog_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> AdminDialogDetail:
    return await container.admin.dialog_detail(user, dialog_id)


@router.post(
    "/dialogs/{dialog_id}/candidate",
    response_model=KnowledgeCandidateDto,
    tags=["Admin Dialogs"],
)
async def create_candidate(
    dialog_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeCandidateDto:
    return await container.moderation.create_by_admin(user, dialog_id)


@router.get(
    "/candidates/{candidate_id}",
    response_model=KnowledgeCandidateDto,
    tags=["Admin Dialogs"],
)
async def candidate(
    candidate_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeCandidateDto:
    return await container.moderation.get_candidate(user, candidate_id)


@router.patch(
    "/candidates/{candidate_id}",
    response_model=KnowledgeCandidateDto,
    tags=["Admin Dialogs"],
)
async def patch_candidate(
    candidate_id: uuid.UUID,
    payload: CandidatePatch,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeCandidateDto:
    return await container.moderation.patch_candidate(
        user, candidate_id, payload.generated_card
    )


@router.post(
    "/candidates/{candidate_id}/approve",
    response_model=KnowledgeCandidateDto,
    tags=["Admin Dialogs"],
)
async def approve_candidate(
    candidate_id: uuid.UUID,
    payload: CandidateApproveRequest | None = Body(default=None),
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeCandidateDto:
    return await container.moderation.approve(
        user, candidate_id, payload.section_id if payload else None
    )


@router.post(
    "/candidates/{candidate_id}/reject",
    response_model=KnowledgeCandidateDto,
    tags=["Admin Dialogs"],
)
async def reject_candidate(
    candidate_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeCandidateDto:
    return await container.moderation.reject(user, candidate_id)


@router.delete(
    "/dialogs/{dialog_id}",
    status_code=204,
    response_model=None,
    tags=["Admin Dialogs"],
)
async def delete_dialog(
    dialog_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> None:
    await container.moderation.hard_delete_dialog(user, dialog_id)


@router.get("/monitoring", response_model=MonitoringResponse, tags=["Monitoring"])
async def monitoring(
    period: MonitoringPeriod = MonitoringPeriod.DAYS_7,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> MonitoringResponse:
    return await container.admin.monitoring(user, period)
