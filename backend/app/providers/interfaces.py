from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.contracts.schemas import SourceRef


@dataclass(frozen=True, slots=True)
class HybridEmbedding:
    dense: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]


class EmbeddingProvider(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[HybridEmbedding]: ...

    async def embed_query(self, text: str) -> HybridEmbedding: ...


@dataclass(frozen=True, slots=True)
class VectorPoint:
    vector_id: uuid.UUID
    dense: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VectorHit:
    vector_id: uuid.UUID
    score: float


class VectorStore(Protocol):
    async def ensure_collection(self) -> None: ...

    async def upsert(self, points: list[VectorPoint]) -> None: ...

    async def search(self, query: HybridEmbedding, limit: int) -> list[VectorHit]: ...

    async def delete_points(self, vector_ids: list[uuid.UUID]) -> None: ...

    async def delete_document(self, document_id: uuid.UUID) -> None: ...

    async def set_document_payload(
        self, document_id: uuid.UUID, payload: dict[str, Any]
    ) -> None: ...


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class ParsedChunk:
    text: str
    heading_path: list[str] = field(default_factory=list)
    page: int | None = None


class PermanentDocumentParser(Protocol):
    async def parse(self, path: Path) -> list[ParsedChunk]: ...


@dataclass(frozen=True, slots=True)
class ChatTurn:
    role: str
    text: str


@dataclass(frozen=True, slots=True)
class Evidence:
    source: SourceRef
    text: str


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    system_prompt: str
    current_text: str
    history: tuple[ChatTurn, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    threshold: float = 0.8
    attachment_file_ids: tuple[str, ...] = ()
    attachment_mime_types: tuple[str, ...] = ()
    screenshot_extracted_text: str | None = None
    screenshot_visual_summary: str | None = None


@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    confidence: float


@dataclass(frozen=True, slots=True)
class ScreenshotAnalysis:
    extracted_text: str
    visual_summary: str


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    precached_prompt_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class StreamChunk:
    text: str
    usage: ProviderUsage | None = None


class LLMProvider(Protocol):
    async def upload_file(
        self,
        file_name: str,
        content: bytes,
        model: str,
        session_id: uuid.UUID | None = None,
    ) -> str: ...

    async def delete_file(
        self,
        file_id: str,
        model: str,
        session_id: uuid.UUID | None = None,
    ) -> None: ...

    async def analyze_screenshot(
        self,
        file_id: str,
        question: str,
        model: str,
        session_id: uuid.UUID,
    ) -> ScreenshotAnalysis: ...

    async def assess_confidence(
        self,
        request: GenerationRequest,
        model: str,
        session_id: uuid.UUID,
    ) -> ConfidenceAssessment: ...

    def stream_text(
        self,
        request: GenerationRequest,
        model: str,
        max_output_tokens: int,
        session_id: uuid.UUID,
    ) -> AsyncIterator[StreamChunk]: ...


class ProviderError(Exception):
    default_message = "Ошибка провайдера GigaChat"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class ProviderUnavailableError(ProviderError):
    default_message = "Провайдер GigaChat недоступен"


class ProviderAuthenticationError(ProviderError):
    default_message = "Ошибка авторизации GigaChat"


class ProviderRateLimitError(ProviderError):
    default_message = "Лимит запросов GigaChat временно исчерпан"


class ProviderBadRequestError(ProviderError):
    default_message = "GigaChat отклонил содержимое запроса"


class ProviderForbiddenError(ProviderError):
    default_message = "Доступ к выбранной модели GigaChat запрещён"


class ProviderNotFoundError(ProviderError):
    default_message = "Ресурс GigaChat не найден"


class ProviderPayloadTooLargeError(ProviderError):
    default_message = "Вложение не помещается в контекст GigaChat"


class ProviderServerError(ProviderError):
    default_message = "GigaChat временно недоступен"


class ProviderPolicyError(ProviderError):
    default_message = (
        "GigaChat не может обработать запрос из-за тематических ограничений"
    )


class StorageError(Exception):
    """Object storage operation failed."""


class VectorStoreError(Exception):
    """Qdrant operation failed."""


class EmbeddingError(Exception):
    """BGE-M3 operation failed."""


class DocumentParsingError(Exception):
    """Docling parsing/chunking failed."""
