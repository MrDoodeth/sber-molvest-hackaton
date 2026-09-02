from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_container, get_current_user
from app.api.openapi import (
    OPERATOR_DIALOG_SSE_RESPONSE,
    OPERATOR_QUEUE_SSE_RESPONSE,
    PROTECTED_RESPONSES,
)
from app.api.sse import SSE_HEADERS, event_stream
from app.contracts.schemas import DialogDetail, DialogSummary, OperatorDraftDto
from app.core.enums import UserRole
from app.core.errors import ForbiddenError
from app.models import User
from app.services.broker import OPERATOR_QUEUE_CHANNEL, operator_dialog_channel
from app.services.container import ApplicationContainer

router = APIRouter(
    prefix="/operator",
    tags=["Operator"],
    responses=PROTECTED_RESPONSES,
)


@router.get("/dialogs", response_model=list[DialogSummary])
async def operator_dialogs(
    scope: str = Query(pattern="^(unassigned|mine)$"),
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> list[DialogSummary]:
    return await container.dialogs.operator_queue(user, scope)


@router.post(
    "/dialogs/{dialog_id}/claim",
    response_model=DialogDetail,
    response_model_exclude_none=True,
    summary="Atomically claim an unassigned escalated ticket",
)
async def claim_dialog(
    dialog_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> DialogDetail:
    return await container.dialogs.claim(user, dialog_id)


@router.get("/dialogs/{dialog_id}/draft", response_model=OperatorDraftDto | None)
async def latest_draft(
    dialog_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> OperatorDraftDto | None:
    return await container.dialogs.latest_operator_draft(user, dialog_id)


@router.get(
    "/events",
    response_class=StreamingResponse,
    summary="Stream operator queue events",
    responses={200: OPERATOR_QUEUE_SSE_RESPONSE},
)
async def operator_events(
    request: Request,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> StreamingResponse:
    if user.role != UserRole.OPERATOR:
        raise ForbiddenError("Operator SSE доступен только оператору")
    return StreamingResponse(
        event_stream(
            request,
            container.broker,
            OPERATOR_QUEUE_CHANNEL,
            container.settings.sse_heartbeat_seconds,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/dialogs/{dialog_id}/events",
    response_class=StreamingResponse,
    summary="Stream private operator draft events",
    responses={200: OPERATOR_DIALOG_SSE_RESPONSE},
)
async def operator_dialog_events(
    dialog_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> StreamingResponse:
    await container.dialogs.assert_operator_sse_access(user, dialog_id)
    return StreamingResponse(
        event_stream(
            request,
            container.broker,
            operator_dialog_channel(dialog_id),
            container.settings.sse_heartbeat_seconds,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
