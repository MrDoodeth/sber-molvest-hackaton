from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse

from app.api.deps import get_container, get_current_user
from app.api.openapi import PROTECTED_RESPONSES, USER_SSE_RESPONSE
from app.api.sse import SSE_HEADERS, event_stream
from app.contracts.schemas import (
    DialogDetail,
    DialogSummary,
    FeedbackDto,
    FeedbackRequest,
    KnowledgeCandidateDto,
    MessageDto,
    MessagePage,
)
from app.models import User
from app.services.attachments import validate_upload
from app.services.broker import user_dialog_channel
from app.services.container import ApplicationContainer

router = APIRouter(tags=["Dialogs"], responses=PROTECTED_RESPONSES)


@router.get("/dialogs", response_model=list[DialogSummary])
async def list_dialogs(
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> list[DialogSummary]:
    return await container.dialogs.list_user_dialogs(user)


@router.post(
    "/dialogs",
    response_model=DialogDetail,
    response_model_exclude_none=True,
    status_code=201,
)
async def create_dialog(
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> DialogDetail:
    return await container.dialogs.create_dialog(user)


@router.get(
    "/dialogs/{dialog_id}",
    response_model=DialogDetail,
    response_model_exclude_none=True,
)
async def get_dialog(
    dialog_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> DialogDetail:
    return await container.dialogs.get_dialog(user, dialog_id)


@router.get("/dialogs/{dialog_id}/messages", response_model=MessagePage)
async def list_messages(
    dialog_id: uuid.UUID,
    cursor: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> MessagePage:
    return await container.dialogs.list_messages(user, dialog_id, cursor, limit)


@router.post(
    "/dialogs/{dialog_id}/messages",
    response_model=MessageDto,
    status_code=201,
    summary="Persist a message and schedule AI processing",
    description=(
        "Multipart command. `text` may be empty only when one attachment is "
        "present. A repeated `(dialog_id, client_message_id)` returns the same "
        "persisted message with `200` and does not duplicate generation."
    ),
    responses={
        200: {
            "model": MessageDto,
            "description": "Idempotent retry; the existing message is returned.",
        }
    },
)
async def send_message(
    dialog_id: uuid.UUID,
    response: Response,
    client_message_id: uuid.UUID = Form(
        description="Stable UUID reused for network retries."
    ),
    text: str = Form(
        default="",
        description="Message text; optional only when attachment is present.",
    ),
    attachment: UploadFile | None = File(
        default=None,
        description=(
            "At most one runtime image (PNG/JPEG, 15 MB) or supported document (40 MB)."
        ),
    ),
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> MessageDto:
    validated = None
    if attachment is not None:
        read_limit = max(
            container.settings.runtime_image_max_bytes,
            container.settings.runtime_document_max_bytes,
        )
        data = await attachment.read(read_limit + 1)
        validated = validate_upload(
            file_name=attachment.filename,
            content_type=attachment.content_type,
            data=data,
            permanent=False,
            settings=container.settings,
        )
    message, created = await container.dialogs.persist_message(
        requester=user,
        dialog_id=dialog_id,
        client_message_id=client_message_id,
        text=text,
        upload=validated,
    )
    response.status_code = 201 if created else 200
    return message


@router.post(
    "/dialogs/{dialog_id}/close",
    response_model=DialogDetail,
    response_model_exclude_none=True,
)
async def close_dialog(
    dialog_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> DialogDetail:
    return await container.dialogs.close(user, dialog_id)


@router.post("/dialogs/{dialog_id}/feedback", response_model=FeedbackDto)
async def add_feedback(
    dialog_id: uuid.UUID,
    payload: FeedbackRequest,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> FeedbackDto:
    feedback, _ = await container.moderation.add_feedback(
        user, dialog_id, payload.verdict
    )
    return feedback


@router.post(
    "/dialogs/{dialog_id}/knowledge-candidate",
    response_model=KnowledgeCandidateDto,
)
async def propose_candidate(
    dialog_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> KnowledgeCandidateDto:
    return await container.moderation.propose_by_operator(user, dialog_id)


@router.get(
    "/dialogs/{dialog_id}/events",
    response_class=StreamingResponse,
    summary="Stream user-safe dialog events",
    responses={200: USER_SSE_RESPONSE},
)
async def dialog_events(
    dialog_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> StreamingResponse:
    await container.dialogs.assert_user_sse_access(user, dialog_id)
    return StreamingResponse(
        event_stream(
            request,
            container.broker,
            user_dialog_channel(dialog_id),
            container.settings.sse_heartbeat_seconds,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/attachments/{attachment_id}",
    summary="Download an authorized dialog attachment",
    responses={
        200: {
            "description": "Original attachment bytes.",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def download_attachment(
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    container: ApplicationContainer = Depends(get_container),
) -> Response:
    data, mime_type, file_name = await container.dialogs.read_attachment(
        user, attachment_id
    )
    encoded_name = quote(file_name)
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Content-Disposition": (f"attachment; filename*=UTF-8''{encoded_name}")
        },
    )
