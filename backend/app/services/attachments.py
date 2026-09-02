from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import PurePath

from app.core.config import Settings
from app.core.errors import UnprocessableError
from app.providers.interfaces import LLMProvider, ObjectStorage

MAX_RUNTIME_ATTACHMENTS = 10
MAX_RUNTIME_IMAGE_REQUEST_BYTES = 80 * 1024 * 1024

RUNTIME_TYPES: dict[str, set[str]] = {
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
    ".bmp": {"image/bmp"},
    ".txt": {"text/plain"},
    ".doc": {"application/msword"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    ".pdf": {"application/pdf"},
    ".epub": {"application/epub+zip"},
    ".ppt": {"application/vnd.ms-powerpoint"},
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    },
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
}

PERMANENT_TYPES: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    ".html": {"text/html"},
    ".htm": {"text/html"},
    ".md": {"text/markdown", "text/plain"},
    ".markdown": {"text/markdown", "text/plain"},
}


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    file_name: str
    extension: str
    mime_type: str
    data: bytes

    @property
    def is_screenshot(self) -> bool:
        return self.mime_type in {"image/png", "image/jpeg"}

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")


def safe_file_name(raw_name: str | None) -> str:
    name = PurePath(raw_name or "attachment").name
    name = re.sub(r"[^\w.() -]", "_", name, flags=re.UNICODE).strip(" .")
    return (name or "attachment")[-180:]


def validate_upload(
    *,
    file_name: str | None,
    content_type: str | None,
    data: bytes,
    permanent: bool,
    settings: Settings,
) -> ValidatedUpload:
    safe_name = safe_file_name(file_name)
    extension = PurePath(safe_name).suffix.lower()
    mime_type = (content_type or "").split(";", 1)[0].strip().lower()
    allowed = PERMANENT_TYPES if permanent else RUNTIME_TYPES
    if extension not in allowed or mime_type not in allowed[extension]:
        raise UnprocessableError(
            "Неподдерживаемый тип файла",
            {"file_name": safe_name, "mime_type": mime_type},
        )
    if not data:
        raise UnprocessableError("Файл пуст")
    if permanent:
        max_size = settings.permanent_document_max_bytes
    elif mime_type.startswith("image/"):
        max_size = settings.runtime_image_max_bytes
    else:
        max_size = settings.runtime_document_max_bytes
    if len(data) > max_size:
        raise UnprocessableError(
            "Файл превышает допустимый размер",
            {"max_bytes": max_size, "actual_bytes": len(data)},
        )
    if mime_type == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise UnprocessableError("Содержимое файла не является PNG")
    if mime_type == "image/jpeg" and not data.startswith(b"\xff\xd8\xff"):
        raise UnprocessableError("Содержимое файла не является JPEG")
    if mime_type == "application/pdf" and not data.startswith(b"%PDF"):
        raise UnprocessableError("Содержимое файла не является PDF")
    return ValidatedUpload(
        file_name=safe_name,
        extension=extension,
        mime_type=mime_type,
        data=data,
    )


class AttachmentService:
    def __init__(
        self,
        storage: ObjectStorage,
        llm_provider: LLMProvider,
        settings: Settings,
    ) -> None:
        self.storage = storage
        self.llm_provider = llm_provider
        self.settings = settings

    async def store_runtime(
        self, message_id: uuid.UUID, upload: ValidatedUpload
    ) -> str:
        # Keep the original filename in the last path segment while allowing
        # multiple files with the same name in one message.
        key = f"attachments/{message_id}/{uuid.uuid4()}/{upload.file_name}"
        await self.storage.put(key, upload.data, upload.mime_type)
        return key

    async def cleanup_local(self, storage_keys: list[str]) -> None:
        for key in storage_keys:
            await self.storage.delete(key)

    async def cleanup_remote(
        self,
        file_ids: list[str],
        active_model: str,
        session_id: uuid.UUID,
    ) -> None:
        for file_id in file_ids:
            await self.llm_provider.delete_file(file_id, active_model, session_id)
