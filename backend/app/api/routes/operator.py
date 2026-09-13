from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_container, get_request_actor
from app.api.openapi import (
    API_RESPONSES,
    OPERATOR_DIALOG_SSE_RESPONSE,
    OPERATOR_QUEUE_SSE_RESPONSE,
)
from app.api.sse import SSE_HEADERS, event_stream, operator_dialog_event_stream
from app.contracts.schemas import (
    DialogDetail,
    DialogSummary,
    OperatorTemplateDto,
)
from app.core.enums import UserRole
from app.core.errors import ForbiddenError
from app.models import User
from app.services.broker import OPERATOR_QUEUE_CHANNEL, operator_dialog_channel
from app.services.container import ApplicationContainer

router = APIRouter(
    prefix="/operator",
    tags=["Operator"],
    responses=API_RESPONSES,
)


@router.get("/dialogs", response_model=list[DialogSummary])
async def operator_dialogs(
    scope: str = Query(pattern="^(unassigned|mine)$"),
    user: User = Depends(get_request_actor),
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
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> DialogDetail:
    return await container.dialogs.claim(user, dialog_id)


@router.post(
    "/dialogs/{dialog_id}/template",
    response_model=OperatorTemplateDto,
    summary=(
        "Generate an editable operator response template from the latest dialog history"
    ),
)
async def generate_template(
    dialog_id: uuid.UUID,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> OperatorTemplateDto:
    return await container.dialogs.generate_operator_template(user, dialog_id)


@router.get(
    "/events",
    response_class=StreamingResponse,
    summary="Stream operator queue events",
    responses={200: OPERATOR_QUEUE_SSE_RESPONSE},
)
async def operator_events(
    request: Request,
    user: User = Depends(get_request_actor),
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
    summary="Stream private operator dialog events",
    responses={200: OPERATOR_DIALOG_SSE_RESPONSE},
)
async def operator_dialog_events(
    dialog_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> StreamingResponse:
    await container.dialogs.assert_operator_sse_access(user, dialog_id)
    detail = await container.dialogs.get_dialog(user, dialog_id)
    messages = await container.dialogs.list_messages(user, dialog_id, None, 200)
    return StreamingResponse(
        operator_dialog_event_stream(
            request,
            container.broker,
            operator_dialog_channel(dialog_id),
            container.settings.sse_heartbeat_seconds,
            str(user.id),
            lambda: container.dialogs.has_operator_sse_access(user, dialog_id),
            {
                "type": "dialog_sync",
                "dialog": detail.model_dump(mode="json"),
                "messages": [item.model_dump(mode="json") for item in messages.items],
            },
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
