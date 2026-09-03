from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.mappers import prompt_dto
from app.contracts.schemas import (
    AdminSettingsResponse,
    AdminSettingsUpdate,
    ModelOptionDto,
    PromptDto,
    SettingsCapabilities,
)
from app.core.config import (
    EMBEDDING_CONTEXT_LIMIT,
    MODEL_CAPABILITIES,
)
from app.core.enums import PromptType
from app.core.errors import NotFoundError, UnprocessableError
from app.models import SystemPrompt, SystemSetting, User
from app.services.seeds import DEFAULT_SETTINGS


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    active_model: str
    gigachat_context_ratio: float
    gigachat_max_output_tokens: int
    embedding_context_ratio: float
    rag_top_k: int
    operator_escalation_threshold: float

    @property
    def model_context_limit(self) -> int:
        return MODEL_CAPABILITIES[self.active_model].context_limit

    @property
    def gigachat_total_budget(self) -> int:
        return math.floor(self.model_context_limit * self.gigachat_context_ratio)

    @property
    def gigachat_input_budget(self) -> int:
        return self.gigachat_total_budget - self.gigachat_max_output_tokens

    @property
    def embedding_input_budget(self) -> int:
        return math.floor(EMBEDDING_CONTEXT_LIMIT * self.embedding_context_ratio)


class SettingsService:
    async def get_runtime(self, session: AsyncSession) -> RuntimeSettings:
        rows = (await session.scalars(select(SystemSetting))).all()
        values: dict[str, Any] = dict(DEFAULT_SETTINGS)
        threshold = next(
            (row.value for row in rows if row.key == "operator_escalation_threshold"),
            DEFAULT_SETTINGS["operator_escalation_threshold"],
        )
        values["operator_escalation_threshold"] = threshold
        runtime = RuntimeSettings(
            active_model=str(values["active_gigachat_model"]),
            gigachat_context_ratio=float(values["gigachat_context_ratio"]),
            gigachat_max_output_tokens=int(values["gigachat_max_output_tokens"]),
            embedding_context_ratio=float(values["embedding_context_ratio"]),
            rag_top_k=int(values["rag_top_k"]),
            operator_escalation_threshold=float(
                values["operator_escalation_threshold"]
            ),
        )
        self._validate(runtime)
        return runtime

    async def get_response(self, session: AsyncSession) -> AdminSettingsResponse:
        runtime = await self.get_runtime(session)
        return AdminSettingsResponse(
            active_model=runtime.active_model,
            gigachat_context_ratio=runtime.gigachat_context_ratio,
            gigachat_max_output_tokens=runtime.gigachat_max_output_tokens,
            embedding_context_ratio=runtime.embedding_context_ratio,
            rag_top_k=runtime.rag_top_k,
            operator_escalation_threshold=runtime.operator_escalation_threshold,
            capabilities=SettingsCapabilities(
                gigachat_context_limit=runtime.model_context_limit,
                embedding_context_limit=EMBEDDING_CONTEXT_LIMIT,
            ),
            available_models=[
                ModelOptionDto(
                    id=capabilities.api_model_id,
                    label=capabilities.label,
                    context_limit=capabilities.context_limit,
                )
                for capabilities in MODEL_CAPABILITIES.values()
            ],
        )

    async def update(
        self, session: AsyncSession, payload: AdminSettingsUpdate
    ) -> AdminSettingsResponse:
        runtime = RuntimeSettings(
            active_model=str(DEFAULT_SETTINGS["active_gigachat_model"]),
            gigachat_context_ratio=float(
                str(DEFAULT_SETTINGS["gigachat_context_ratio"])
            ),
            gigachat_max_output_tokens=int(
                str(DEFAULT_SETTINGS["gigachat_max_output_tokens"])
            ),
            embedding_context_ratio=float(
                str(DEFAULT_SETTINGS["embedding_context_ratio"])
            ),
            rag_top_k=int(str(DEFAULT_SETTINGS["rag_top_k"])),
            operator_escalation_threshold=payload.operator_escalation_threshold,
        )
        self._validate(runtime)
        row = await session.get(
            SystemSetting, "operator_escalation_threshold", with_for_update=True
        )
        if row is None:
            session.add(
                SystemSetting(
                    key="operator_escalation_threshold",
                    value=runtime.operator_escalation_threshold,
                )
            )
        else:
            row.value = runtime.operator_escalation_threshold
        await session.commit()
        return await self.get_response(session)

    @staticmethod
    def _validate(runtime: RuntimeSettings) -> None:
        if runtime.active_model not in MODEL_CAPABILITIES:
            raise UnprocessableError(
                "Неизвестная модель GigaChat",
                {"active_model": runtime.active_model},
            )
        if not 0 <= runtime.gigachat_context_ratio <= 1:
            raise UnprocessableError("gigachatContextRatio должен быть от 0 до 1")
        if not 0 <= runtime.embedding_context_ratio <= 1:
            raise UnprocessableError("embeddingContextRatio должен быть от 0 до 1")
        if not 0 <= runtime.operator_escalation_threshold <= 1:
            raise UnprocessableError(
                "operatorEscalationThreshold должен быть от 0 до 1"
            )
        if runtime.rag_top_k < 1:
            raise UnprocessableError("ragTopK должен быть не меньше 1")
        total_budget = math.floor(
            MODEL_CAPABILITIES[runtime.active_model].context_limit
            * runtime.gigachat_context_ratio
        )
        if not 0 < runtime.gigachat_max_output_tokens < total_budget:
            raise UnprocessableError(
                "gigachatMaxOutputTokens должен быть меньше общего бюджета контекста",
                {"gigachat_total_budget": total_budget},
            )


class PromptService:
    async def list_active(self, session: AsyncSession) -> list[PromptDto]:
        prompts = (
            await session.scalars(select(SystemPrompt).order_by(SystemPrompt.type))
        ).all()
        updater_ids = {prompt.updated_by for prompt in prompts if prompt.updated_by}
        users = {}
        if updater_ids:
            users = {
                user.id: user
                for user in (
                    await session.scalars(select(User).where(User.id.in_(updater_ids)))
                ).all()
            }
        return [
            prompt_dto(
                prompt,
                users.get(prompt.updated_by) if prompt.updated_by is not None else None,
            )
            for prompt in prompts
        ]

    async def get_active(
        self, session: AsyncSession, prompt_type: PromptType
    ) -> SystemPrompt:
        prompt = await session.scalar(
            select(SystemPrompt).where(
                SystemPrompt.type == prompt_type,
            )
        )
        if prompt is None:
            raise NotFoundError(f"Активный prompt {prompt_type.value} не найден")
        return prompt

    async def update(
        self,
        session: AsyncSession,
        prompt_type: PromptType,
        content: str,
        updated_by: uuid.UUID,
    ) -> PromptDto:
        current = await session.scalar(
            select(SystemPrompt)
            .where(SystemPrompt.type == prompt_type)
            .with_for_update()
        )
        if current is None:
            current = SystemPrompt(
                type=prompt_type,
                content=content,
                updated_by=updated_by,
            )
            session.add(current)
        else:
            current.content = content
            current.updated_by = updated_by
            current.updated_at = datetime.now(UTC)
        await session.commit()
        updater = await session.get(User, updated_by)
        return prompt_dto(current, updater)
