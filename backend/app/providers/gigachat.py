from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.providers.interfaces import (
    ConfidenceAssessment,
    GenerationRequest,
    ProviderAuthenticationError,
    ProviderBadRequestError,
    ProviderError,
    ProviderForbiddenError,
    ProviderNotFoundError,
    ProviderPayloadTooLargeError,
    ProviderPolicyError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderUnavailableError,
    ProviderUsage,
    ScreenshotAnalysis,
    StreamChunk,
)


class _ConfidenceSchema(BaseModel):
    confidence: float = Field(ge=0, le=1)


class _ScreenshotSchema(BaseModel):
    extracted_text: str
    visual_summary: str


class GigaChatProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients: dict[tuple[str, int], Any] = {}

    def _require_credentials(self) -> str:
        if self._settings.gigachat_credentials is None:
            raise ProviderUnavailableError(
                "Провайдер GigaChat недоступен: не заданы GIGACHAT_CREDENTIALS"
            )
        return self._settings.gigachat_credentials.get_secret_value()

    def _client(self, model: str, max_tokens: int) -> Any:
        credentials = self._require_credentials()
        key = (model, max_tokens)
        if key in self._clients:
            return self._clients[key]
        try:
            from langchain_gigachat import GigaChat
        except ImportError as exc:
            raise ProviderUnavailableError(
                "Провайдер GigaChat недоступен: langchain-gigachat не установлен"
            ) from exc
        options: dict[str, Any] = {
            "credentials": credentials,
            "scope": self._settings.gigachat_scope,
            "model": model,
            "max_tokens": max_tokens,
            "verify_ssl_certs": True,
            "max_retries": self._settings.gigachat_max_retries,
            "retry_backoff_factor": self._settings.gigachat_retry_backoff_factor,
        }
        if self._settings.gigachat_ca_bundle_file is not None:
            options["ca_bundle_file"] = str(self._settings.gigachat_ca_bundle_file)
        self._clients[key] = GigaChat(**options)
        return self._clients[key]

    @contextlib.contextmanager
    def _request_headers(
        self,
        session_id: uuid.UUID,
        request_id: uuid.UUID | None = None,
    ) -> Iterator[None]:
        tokens: list[tuple[Any, Any]] = []
        actual_request_id = request_id or uuid.uuid4()
        try:
            try:
                from gigachat.context import request_id_cvar, session_id_cvar

                tokens.append((session_id_cvar, session_id_cvar.set(str(session_id))))
                tokens.append(
                    (request_id_cvar, request_id_cvar.set(str(actual_request_id)))
                )
            except (ImportError, AttributeError):
                # Older SDK builds may not expose context vars; LangChain still works
                # and retains its own request metadata.
                tokens = []
            yield
        finally:
            for variable, token in reversed(tokens):
                variable.reset(token)

    def _messages(self, request: GenerationRequest) -> list[Any]:
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        except ImportError as exc:
            raise ProviderUnavailableError("langchain-core не установлен") from exc

        evidence = (
            "\n\n".join(
                f"[{item.source.label}] {item.source.title}\n{item.text}"
                for item in request.evidence
            )
            or "Источники не найдены."
        )
        screenshot = ""
        if request.screenshot_extracted_text or request.screenshot_visual_summary:
            screenshot = (
                "\n\nSCREENSHOT ANALYSIS\n"
                f"Извлечённый текст: {request.screenshot_extracted_text or ''}\n"
                f"Визуальное описание: {request.screenshot_visual_summary or ''}"
            )
        system = (
            f"{request.system_prompt}\n\n"
            "CURRENT SETTINGS\n"
            f"operator_escalation_threshold = {request.threshold}\n\n"
            f"KNOWLEDGE EVIDENCE\n{evidence}{screenshot}"
        )
        messages: list[Any] = [SystemMessage(content=system)]
        for turn in request.history:
            if turn.role in {"assistant", "operator"}:
                messages.append(AIMessage(content=turn.text))
            elif turn.role == "system":
                messages.append(SystemMessage(content=turn.text))
            else:
                messages.append(HumanMessage(content=turn.text))

        current_text = request.current_text or "Проанализируй приложенный файл."
        if request.attachment_file_id:
            block_type = (
                "image"
                if (request.attachment_mime_type or "").startswith("image/")
                else "file"
            )
            # GigaChat's file_id blocks extend LangChain's current TypedDict union.
            content_blocks: list[Any] = [
                {"type": "text", "text": current_text},
                {
                    "type": block_type,
                    "file_id": request.attachment_file_id,
                },
            ]
            messages.append(HumanMessage(content_blocks=content_blocks))
        else:
            messages.append(HumanMessage(content=current_text))
        return messages

    async def _structured(
        self,
        *,
        client: Any,
        schema: type[BaseModel],
        messages: list[Any],
        session_id: uuid.UUID,
    ) -> BaseModel:
        for method in ("json_schema", "function_calling"):
            try:
                runnable = client.with_structured_output(
                    schema,
                    method=method,
                    include_raw=True,
                )
                request_id = uuid.uuid4()
                with self._request_headers(session_id, request_id):
                    result = await runnable.ainvoke(
                        messages,
                        config={
                            "metadata": {
                                "session_id": str(session_id),
                                "request_id": str(request_id),
                            }
                        },
                    )
                if isinstance(result, dict) and "raw" in result:
                    raw = result.get("raw")
                    metadata = getattr(raw, "response_metadata", None) or {}
                    if metadata.get("finish_reason") == "blacklist":
                        raise ProviderPolicyError()
                    parsing_error = result.get("parsing_error")
                    if parsing_error is not None:
                        raise parsing_error
                    parsed = result.get("parsed")
                    if parsed is None:
                        raise ProviderBadRequestError(
                            "GigaChat не вернул structured result"
                        )
                    return schema.model_validate(parsed)
                return schema.model_validate(result)
            except Exception as exc:
                if isinstance(exc, ProviderPolicyError):
                    raise
                if method == "json_schema" and self._supports_schema_fallback(exc):
                    continue
                raise self._map_error(exc) from exc
        raise ProviderBadRequestError(
            "Structured output недоступен для выбранной модели"
        )

    @staticmethod
    def _supports_schema_fallback(exc: Exception) -> bool:
        names = {base.__name__ for base in type(exc).mro()}
        return bool(names & {"BadRequestError", "ValidationError", "ValueError"})

    async def upload_file(
        self,
        file_name: str,
        content: bytes,
        model: str,
        session_id: uuid.UUID | None = None,
    ) -> str:
        client = self._client(model, 64)
        try:
            with self._request_headers(session_id or uuid.uuid4()):
                uploaded = await client.aupload_file(
                    (file_name, content),
                    purpose="general",
                )
            file_id = getattr(uploaded, "id_", None) or getattr(uploaded, "id", None)
            if not file_id:
                raise ProviderServerError("GigaChat не вернул file_id")
            return str(file_id)
        except ProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc) from exc

    async def delete_file(
        self,
        file_id: str,
        model: str,
        session_id: uuid.UUID | None = None,
    ) -> None:
        client = self._client(model, 64)
        try:
            with self._request_headers(session_id or uuid.uuid4()):
                await client.adelete_file(file_id)
        except Exception as exc:
            mapped = self._map_error(exc)
            if isinstance(mapped, ProviderNotFoundError):
                return
            raise mapped from exc

    async def analyze_screenshot(
        self,
        file_id: str,
        question: str,
        model: str,
        session_id: uuid.UUID,
    ) -> ScreenshotAnalysis:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError as exc:
            raise ProviderUnavailableError("langchain-core не установлен") from exc
        screenshot_blocks: list[Any] = [
            {"type": "text", "text": question or "Проанализируй скриншот."},
            {"type": "image", "file_id": file_id},
        ]
        messages = [
            SystemMessage(
                content=(
                    "Извлеки текст, код ошибки и значимые элементы интерфейса 1С "
                    "со скриншота. Сформируй только структурированный результат; "
                    "не предлагай решение проблемы."
                )
            ),
            HumanMessage(content_blocks=screenshot_blocks),
        ]
        result = await self._structured(
            client=self._client(model, 512),
            schema=_ScreenshotSchema,
            messages=messages,
            session_id=session_id,
        )
        parsed = _ScreenshotSchema.model_validate(result)
        return ScreenshotAnalysis(
            extracted_text=parsed.extracted_text,
            visual_summary=parsed.visual_summary,
        )

    async def assess_confidence(
        self,
        request: GenerationRequest,
        model: str,
        session_id: uuid.UUID,
    ) -> ConfidenceAssessment:
        messages = self._messages(request)
        messages[0].content += (
            "\n\nCONFIDENCE GATE\nВерни только confidence от 0 до 1. "
            "Если пользователь явно просит оператора, верни 0."
        )
        result = await self._structured(
            client=self._client(model, 64),
            schema=_ConfidenceSchema,
            messages=messages,
            session_id=session_id,
        )
        parsed = _ConfidenceSchema.model_validate(result)
        return ConfidenceAssessment(confidence=parsed.confidence)

    async def stream_text(
        self,
        request: GenerationRequest,
        model: str,
        max_output_tokens: int,
        session_id: uuid.UUID,
    ) -> AsyncIterator[StreamChunk]:
        client = self._client(model, max_output_tokens)
        messages = self._messages(request)
        messages[0].content += (
            "\n\nANSWER OR DRAFT\nВерни только обычный текст ответа или "
            "черновика. Не возвращай JSON и отдельное поле confidence."
        )
        usage: ProviderUsage | None = None
        try:
            request_id = uuid.uuid4()
            with self._request_headers(session_id, request_id):
                async for chunk in client.astream(
                    messages,
                    config={
                        "metadata": {
                            "session_id": str(session_id),
                            "request_id": str(request_id),
                        }
                    },
                ):
                    metadata = getattr(chunk, "response_metadata", None) or {}
                    if metadata.get("finish_reason") == "blacklist":
                        raise ProviderPolicyError()
                    raw_usage = getattr(chunk, "usage_metadata", None)
                    if raw_usage:
                        input_details = raw_usage.get("input_token_details") or {}
                        usage = ProviderUsage(
                            prompt_tokens=raw_usage.get("input_tokens"),
                            completion_tokens=raw_usage.get("output_tokens"),
                            precached_prompt_tokens=input_details.get("cache_read"),
                        )
                    text = self._extract_text(getattr(chunk, "content", ""))
                    if text:
                        yield StreamChunk(text=text)
            if usage is not None:
                yield StreamChunk(text="", usage=usage)
        except ProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc) from exc

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            return "".join(parts)
        return str(content) if content else ""

    @staticmethod
    def _map_error(exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        names = {base.__name__ for base in type(exc).mro()}
        mappings: tuple[tuple[set[str], type[ProviderError]], ...] = (
            ({"AuthenticationError"}, ProviderAuthenticationError),
            ({"RateLimitError"}, ProviderRateLimitError),
            ({"BadRequestError"}, ProviderBadRequestError),
            ({"ForbiddenError"}, ProviderForbiddenError),
            ({"NotFoundError"}, ProviderNotFoundError),
            (
                {"RequestEntityTooLargeError", "UnprocessableEntityError"},
                ProviderPayloadTooLargeError,
            ),
            ({"ServerError", "GigaChatException"}, ProviderServerError),
        )
        for expected, mapped_type in mappings:
            if names & expected:
                return mapped_type()
        return ProviderServerError()
