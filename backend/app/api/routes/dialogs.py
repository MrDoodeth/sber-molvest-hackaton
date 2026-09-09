from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse

from app.api.deps import get_container, get_request_actor
from app.api.openapi import API_RESPONSES, USER_SSE_RESPONSE
from app.api.sse import SSE_HEADERS, event_stream
from app.contracts.schemas import (
    DialogDetail,
    DialogSummary,
    FeedbackDto,
    FeedbackRequest,
    MessageDto,
    MessagePage,
)
from app.core.enums import MessageAuthor
from app.core.errors import UnprocessableError
from app.models import User
from app.services.attachments import (
    MAX_RUNTIME_ATTACHMENTS,
    MAX_RUNTIME_IMAGES,
    MAX_RUNTIME_REQUEST_BYTES,
    ValidatedUpload,
    validate_upload,
)
from app.services.broker import user_dialog_channel
from app.services.container import ApplicationContainer

router = APIRouter(tags=["Dialogs"], responses=API_RESPONSES)


@router.get("/dialogs", response_model=list[DialogSummary])
async def list_dialogs(
    user: User = Depends(get_request_actor),
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
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> DialogDetail:
    return await container.dialogs.create_dialog(user)


@router.delete("/dialogs/{dialog_id}/draft", status_code=204, response_model=None)
async def discard_empty_dialog(
    dialog_id: uuid.UUID,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> None:
    await container.dialogs.discard_empty_dialog(user, dialog_id)


@router.get(
    "/dialogs/{dialog_id}",
    response_model=DialogDetail,
    response_model_exclude_none=True,
)
async def get_dialog(
    dialog_id: uuid.UUID,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> DialogDetail:
    return await container.dialogs.get_dialog(user, dialog_id)


@router.get("/dialogs/{dialog_id}/messages", response_model=MessagePage)
async def list_messages(
    dialog_id: uuid.UUID,
    cursor: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> MessagePage:
    return await container.dialogs.list_messages(user, dialog_id, cursor, limit)


@router.post(
    "/dialogs/{dialog_id}/messages",
    response_model=MessageDto,
    status_code=201,
    summary="Persist a message and schedule AI processing",
    description=(
        "Multipart command. `text` may be empty only when attachments are "
        "present. Up to 10 attachments and one image can be sent in one "
        "message. A repeated "
        "`(dialog_id, client_message_id)` returns the same "
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
    background_tasks: BackgroundTasks,
    client_message_id: uuid.UUID = Form(
        description="Stable UUID reused for network retries."
    ),
    text: str = Form(
        default="",
        description="Message text; optional only when an attachment is present.",
    ),
    attachments: list[UploadFile] | None = File(
        default=None,
        description=(
            "Up to 10 runtime attachments and one image. Images are limited "
            "to 15 MB each; "
            "supported documents to 40 MB each."
        ),
    ),
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> MessageDto:
    uploaded_files = attachments or []
    if len(uploaded_files) > MAX_RUNTIME_ATTACHMENTS:
        raise UnprocessableError(
            "Можно прикрепить не более 10 файлов",
            {"max_files": MAX_RUNTIME_ATTACHMENTS},
        )

    validated: list[ValidatedUpload] = []
    if uploaded_files:
        total_bytes = 0
        image_count = 0
        for attachment in uploaded_files:
            if total_bytes >= MAX_RUNTIME_REQUEST_BYTES:
                raise UnprocessableError(
                    "Суммарный размер вложений должен быть менее 80 МБ",
                    {"max_bytes": MAX_RUNTIME_REQUEST_BYTES},
                )
            individual_limit = (
                container.settings.runtime_image_max_bytes
                if (attachment.content_type or "").startswith("image/")
                else container.settings.runtime_document_max_bytes
            )
            remaining = MAX_RUNTIME_REQUEST_BYTES - total_bytes
            data = await attachment.read(min(individual_limit, remaining) + 1)
            if len(data) >= remaining:
                raise UnprocessableError(
                    "Суммарный размер вложений должен быть менее 80 МБ",
                    {"max_bytes": MAX_RUNTIME_REQUEST_BYTES},
                )
            upload = validate_upload(
                file_name=attachment.filename,
                content_type=attachment.content_type,
                data=data,
                permanent=False,
                settings=container.settings,
            )
            if upload.is_image:
                image_count += 1
                if image_count > MAX_RUNTIME_IMAGES:
                    raise UnprocessableError(
                        "Можно прикрепить только одно изображение за сообщение",
                        {"max_images": MAX_RUNTIME_IMAGES},
                    )
            total_bytes += len(upload.data)
            validated.append(upload)
    message, created = await container.dialogs.persist_message(
        requester=user,
        dialog_id=dialog_id,
        client_message_id=client_message_id,
        text=text,
        uploads=validated,
        defer_processing=True,
    )
    if message.author_type == MessageAuthor.USER:
        background_tasks.add_task(container.dialogs.schedule_processing, message.id)
    response.status_code = 201 if created else 200
    return message


@router.post(
    "/dialogs/{dialog_id}/close",
    response_model=DialogDetail,
    response_model_exclude_none=True,
)
async def close_dialog(
    dialog_id: uuid.UUID,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> DialogDetail:
    return await container.dialogs.close(user, dialog_id)


@router.post("/dialogs/{dialog_id}/feedback", response_model=FeedbackDto)
async def add_feedback(
    dialog_id: uuid.UUID,
    payload: FeedbackRequest,
    user: User = Depends(get_request_actor),
    container: ApplicationContainer = Depends(get_container),
) -> FeedbackDto:
    feedback, _ = await container.moderation.add_feedback(
        user, dialog_id, payload.verdict
    )
    return feedback


@router.get(
    "/dialogs/{dialog_id}/events",
    response_class=StreamingResponse,
    summary="Stream user-safe dialog events",
    responses={200: USER_SSE_RESPONSE},
)
async def dialog_events(
    dialog_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_request_actor),
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
    summary="Download a dialog attachment",
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
    user: User = Depends(get_request_actor),
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
