from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import MessageAuthor
from app.core.errors import (
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableError,
)
from app.models import Attachment, Message
from app.providers.interfaces import (
    ChatTurn,
    EmbeddingError,
    GenerationRequest,
    LLMProvider,
    ProviderServerError,
    StorageError,
    VectorStoreError,
)
from app.services.attachments import RUNTIME_IMAGE_MIME_TYPES, AttachmentService
from app.services.context import ContextBuilder
from app.services.rag import RAGService
from app.services.settings import RuntimeSettings


@dataclass(frozen=True, slots=True)
class PreparedGenerationContext:
    request: GenerationRequest


class GenerationContextService:
    """Build the shared dialog/RAG context for every GigaChat generation flow."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        attachment_service: AttachmentService,
        context_builder: ContextBuilder,
        rag_service: RAGService,
        llm_provider: LLMProvider,
    ) -> None:
        self._session_factory = session_factory
        self._attachment_service = attachment_service
        self._context_builder = context_builder
        self._rag_service = rag_service
        self._llm_provider = llm_provider

    async def build_for_user_message(
        self,
        *,
        dialog_id: uuid.UUID,
        message_id: uuid.UUID,
        system_prompt: str,
        settings: RuntimeSettings,
    ) -> PreparedGenerationContext:
        messages, attachments = await self._dialog_snapshot(dialog_id)
        message = next((item for item in messages if item.id == message_id), None)
        if message is None or message.author_type != MessageAuthor.USER:
            raise NotFoundError("Сообщение пользователя не найдено")
        return await self._build_for_message(
            dialog_id=dialog_id,
            messages=messages,
            attachments=attachments,
            message=message,
            system_prompt=system_prompt,
            settings=settings,
        )

    async def build_for_operator_template(
        self,
        *,
        dialog_id: uuid.UUID,
        system_prompt: str,
        settings: RuntimeSettings,
    ) -> PreparedGenerationContext:
        messages, attachments = await self._dialog_snapshot(dialog_id)
        message = next(
            (
                item
                for item in reversed(messages)
                if item.author_type == MessageAuthor.USER
            ),
            None,
        )
        if message is None:
            raise UnprocessableError(
                "Нельзя сгенерировать шаблон без сообщений пользователя"
            )
        return await self._build_for_message(
            dialog_id=dialog_id,
            messages=messages,
            attachments=attachments,
            message=message,
            system_prompt=system_prompt,
            settings=settings,
        )

    async def build_for_knowledge_card(
        self,
        *,
        dialog_id: uuid.UUID,
        system_prompt: str,
        settings: RuntimeSettings,
        instruction: str,
    ) -> PreparedGenerationContext:
        messages, attachments = await self._dialog_snapshot(dialog_id)
        history = self._history(messages, attachments)
        all_attachments = [
            attachment
            for message in messages
            for attachment in attachments.get(message.id, [])
        ]
        return await self._build_request(
            dialog_id=dialog_id,
            system_prompt=system_prompt,
            current_text=instruction,
            history=history,
            attachments=all_attachments,
            settings=settings,
        )

    async def _build_for_message(
        self,
        *,
        dialog_id: uuid.UUID,
        messages: list[Message],
        attachments: dict[uuid.UUID, list[Attachment]],
        message: Message,
        system_prompt: str,
        settings: RuntimeSettings,
    ) -> PreparedGenerationContext:
        message_index = next(
            index for index, item in enumerate(messages) if item.id == message.id
        )
        return await self._build_request(
            dialog_id=dialog_id,
            system_prompt=system_prompt,
            current_text=message.text,
            history=self._history(messages[:message_index], attachments),
            attachments=attachments.get(message.id, []),
            settings=settings,
        )

    async def _build_request(
        self,
        *,
        dialog_id: uuid.UUID,
        system_prompt: str,
        current_text: str,
        history: list[ChatTurn],
        attachments: list[Attachment],
        settings: RuntimeSettings,
    ) -> PreparedGenerationContext:
        try:
            prompt_search_context = (
                self._context_builder.build_prompt_embedding_context(
                    current_text=current_text,
                    history=history,
                    settings=settings,
                )
            )
            query_embeddings = [
                await self._rag_service.embed_query(prompt_search_context)
            ]
            attachment_file_ids, attachment_mime_types = await self._upload_attachments(
                attachments, settings.active_model, dialog_id
            )
            (
                screenshot_extracted_text,
                screenshot_visual_summary,
            ) = await self._prepare_screenshot(
                attachments,
                current_text,
                settings.active_model,
                dialog_id,
            )
            if screenshot_extracted_text or screenshot_visual_summary:
                screenshot_search_context = (
                    self._context_builder.build_screenshot_embedding_context(
                        extracted_text=screenshot_extracted_text,
                        visual_summary=screenshot_visual_summary,
                        settings=settings,
                    )
                )
                query_embeddings.append(
                    await self._rag_service.embed_query(screenshot_search_context)
                )
            async with self._session_factory() as session:
                retrieval = await self._rag_service.retrieve_embeddings(
                    session,
                    query_embeddings,
                    settings.rag_top_k,
                    weights=[1.0] * len(query_embeddings),
                )
        except StorageError as exc:
            raise ServiceUnavailableError(
                "Хранилище вложений временно недоступно"
            ) from exc
        except (EmbeddingError, VectorStoreError) as exc:
            raise ServiceUnavailableError(
                "Не удалось подготовить контекст из базы знаний"
            ) from exc

        return PreparedGenerationContext(
            request=self._context_builder.build_generation_request(
                system_prompt=system_prompt,
                current_text=current_text,
                history=history,
                evidence=retrieval.evidence,
                attachment_file_ids=attachment_file_ids,
                attachment_mime_types=attachment_mime_types,
                screenshot_extracted_text=screenshot_extracted_text,
                screenshot_visual_summary=screenshot_visual_summary,
                settings=settings,
                rag_status=retrieval.status,
            )
        )

    async def _dialog_snapshot(
        self, dialog_id: uuid.UUID
    ) -> tuple[list[Message], dict[uuid.UUID, list[Attachment]]]:
        async with self._session_factory() as session:
            messages = list(
                await session.scalars(
                    select(Message)
                    .where(Message.dialog_id == dialog_id)
                    .order_by(Message.created_at, Message.id)
                )
            )
            attachments = list(
                await session.scalars(
                    select(Attachment)
                    .join(Message, Attachment.message_id == Message.id)
                    .where(Message.dialog_id == dialog_id)
                )
            )
        by_message: dict[uuid.UUID, list[Attachment]] = {}
        for attachment in attachments:
            by_message.setdefault(attachment.message_id, []).append(attachment)
        return messages, by_message

    async def _upload_attachments(
        self,
        attachments: list[Attachment],
        model: str,
        dialog_id: uuid.UUID,
    ) -> tuple[list[str], list[str]]:
        file_ids: list[str] = []
        mime_types: list[str] = []
        for attachment in attachments:
            file_id = attachment.gigachat_file_id
            if file_id is None or attachment.remote_deleted_at is not None:
                content = await self._attachment_service.storage.get(
                    attachment.storage_key
                )
                file_id = await self._llm_provider.upload_file(
                    PurePosixPath(attachment.storage_key).name,
                    content,
                    model,
                    dialog_id,
                )
                async with self._session_factory() as session:
                    persisted = await session.get(
                        Attachment, attachment.id, with_for_update=True
                    )
                    if persisted is None:
                        await self._llm_provider.delete_file(file_id, model, dialog_id)
                        raise NotFoundError("Вложение не найдено")
                    if (
                        persisted.gigachat_file_id is not None
                        and persisted.remote_deleted_at is None
                    ):
                        await self._llm_provider.delete_file(file_id, model, dialog_id)
                        file_id = persisted.gigachat_file_id
                    else:
                        persisted.gigachat_file_id = file_id
                        persisted.remote_deleted_at = None
                        await session.commit()
                attachment.gigachat_file_id = file_id
                attachment.remote_deleted_at = None
            file_ids.append(file_id)
            mime_types.append(attachment.mime_type)
        return file_ids, mime_types

    async def _prepare_screenshot(
        self,
        attachments: list[Attachment],
        current_text: str,
        model: str,
        dialog_id: uuid.UUID,
    ) -> tuple[str | None, str | None]:
        screenshot = next(
            (
                attachment
                for attachment in attachments
                if attachment.mime_type in RUNTIME_IMAGE_MIME_TYPES
            ),
            None,
        )
        if screenshot is None:
            return None, None
        if (
            screenshot.extracted_text is not None
            and screenshot.visual_summary is not None
        ):
            return screenshot.extracted_text, screenshot.visual_summary
        if screenshot.gigachat_file_id is None:
            raise ProviderServerError("GigaChat file_id не сохранён")
        analysis = await self._llm_provider.analyze_screenshot(
            screenshot.gigachat_file_id,
            current_text,
            model,
            dialog_id,
        )
        async with self._session_factory() as session:
            persisted = await session.get(Attachment, screenshot.id)
            if persisted is not None:
                persisted.extracted_text = analysis.extracted_text
                persisted.visual_summary = analysis.visual_summary
                await session.commit()
        screenshot.extracted_text = analysis.extracted_text
        screenshot.visual_summary = analysis.visual_summary
        return analysis.extracted_text, analysis.visual_summary

    @staticmethod
    def _history(
        messages: list[Message],
        attachments: dict[uuid.UUID, list[Attachment]],
    ) -> list[ChatTurn]:
        history: list[ChatTurn] = []
        for message in messages:
            parts = [message.text]
            for attachment in attachments.get(message.id, []):
                if attachment.extracted_text:
                    parts.append(f"[Текст вложения] {attachment.extracted_text}")
                if attachment.visual_summary:
                    parts.append(f"[Описание вложения] {attachment.visual_summary}")
                if not attachment.extracted_text and not attachment.visual_summary:
                    parts.append(
                        f"[Вложение] {PurePosixPath(attachment.storage_key).name}"
                    )
            text = "\n".join(part for part in parts if part).strip()
            if not text:
                continue
            role = message.author_type.value
            if message.author_type == MessageAuthor.SYSTEM:
                role = MessageAuthor.USER.value
                text = f"[Системное событие] {text}"
            history.append(ChatTurn(role=role, text=text))
        return history
