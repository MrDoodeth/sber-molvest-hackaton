from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath
from typing import BinaryIO, Protocol

from app.core.config import Settings
from app.core.errors import UnprocessableError
from app.providers.interfaces import LLMProvider, ObjectStorage

MAX_RUNTIME_ATTACHMENTS = 10
MAX_RUNTIME_IMAGES = 1
MAX_RUNTIME_REQUEST_BYTES = 80 * 1024 * 1024
RUNTIME_IMAGE_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/tiff", "image/bmp"}
)

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
    ".epub": {"application/epub", "application/epub+zip"},
    ".ppt": {"application/ppt", "application/vnd.ms-powerpoint"},
    ".pptx": {
        "application/pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },
    ".xlsx": {
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
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
    source: BinaryIO
    size_bytes: int
    sha256: str

    @property
    def is_screenshot(self) -> bool:
        return self.mime_type in RUNTIME_IMAGE_MIME_TYPES

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
    safe_name, extension, mime_type, max_size = _upload_metadata(
        file_name, content_type, permanent, settings
    )
    _validate_size(len(data), max_size)
    _validate_signature(mime_type, data[:16])
    return ValidatedUpload(
        file_name=safe_name,
        extension=extension,
        mime_type=mime_type,
        source=BytesIO(data),
        size_bytes=len(data),
        sha256=sha256(data).hexdigest(),
    )


class AsyncUpload(Protocol):
    file: BinaryIO

    async def read(self, size: int = -1) -> bytes: ...

    async def seek(self, offset: int) -> None: ...


async def validate_upload_stream(
    *,
    file_name: str | None,
    content_type: str | None,
    upload: AsyncUpload,
    permanent: bool,
    settings: Settings,
) -> ValidatedUpload:
    safe_name, extension, mime_type, max_size = _upload_metadata(
        file_name, content_type, permanent, settings
    )
    digest = sha256()
    prefix = b""
    size = 0
    while chunk := await upload.read(1024 * 1024):
        size += len(chunk)
        _validate_size(size, max_size)
        digest.update(chunk)
        if len(prefix) < 16:
            prefix = (prefix + chunk)[:16]
    _validate_size(size, max_size)
    _validate_signature(mime_type, prefix)
    await upload.seek(0)
    return ValidatedUpload(
        file_name=safe_name,
        extension=extension,
        mime_type=mime_type,
        source=upload.file,
        size_bytes=size,
        sha256=digest.hexdigest(),
    )


def _upload_metadata(
    file_name: str | None,
    content_type: str | None,
    permanent: bool,
    settings: Settings,
) -> tuple[str, str, str, int]:
    safe_name = safe_file_name(file_name)
    extension = PurePath(safe_name).suffix.lower()
    mime_type = (content_type or "").split(";", 1)[0].strip().lower()
    allowed = PERMANENT_TYPES if permanent else RUNTIME_TYPES
    if extension not in allowed or mime_type not in allowed[extension]:
        raise UnprocessableError(
            "Неподдерживаемый тип файла",
            {"file_name": safe_name, "mime_type": mime_type},
        )
    if permanent:
        max_size = settings.permanent_document_max_bytes
    elif mime_type.startswith("image/"):
        max_size = settings.runtime_image_max_bytes
    else:
        max_size = settings.runtime_document_max_bytes
    return safe_name, extension, mime_type, max_size


def _validate_size(size: int, max_size: int) -> None:
    if size == 0:
        raise UnprocessableError("Файл пуст")
    if size > max_size:
        raise UnprocessableError(
            "Файл превышает допустимый размер",
            {"max_bytes": max_size, "actual_bytes": size},
        )


def _validate_signature(mime_type: str, prefix: bytes) -> None:
    if mime_type == "image/png" and not prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        raise UnprocessableError("Содержимое файла не является PNG")
    if mime_type == "image/jpeg" and not prefix.startswith(b"\xff\xd8\xff"):
        raise UnprocessableError("Содержимое файла не является JPEG")
    if mime_type == "image/tiff" and not (
        prefix.startswith(b"II*\x00") or prefix.startswith(b"MM\x00*")
    ):
        raise UnprocessableError("Содержимое файла не является TIFF")
    if mime_type == "image/bmp" and not prefix.startswith(b"BM"):
        raise UnprocessableError("Содержимое файла не является BMP")
    if mime_type == "application/pdf" and not prefix.startswith(b"%PDF"):
        raise UnprocessableError("Содержимое файла не является PDF")


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
        upload.source.seek(0)
        put_file = getattr(self.storage, "put_file", None)
        if callable(put_file):
            await put_file(key, upload.source, upload.mime_type)
        else:
            await self.storage.put(key, upload.source.read(), upload.mime_type)
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
