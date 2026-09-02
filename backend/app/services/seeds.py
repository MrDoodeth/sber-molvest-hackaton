from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import (
    DEFAULT_CASE_SECTION_ID,
    DEMO_ADMIN_ID,
    DEMO_OPERATOR_ID,
    DEMO_USER_ID,
    DOCUMENTATION_SECTION_ID,
    INTERNAL_KB_SECTION_ID,
)
from app.core.enums import PromptType, UserRole
from app.models import KnowledgeSection, SystemPrompt, SystemSetting, User

DEFAULT_SETTINGS: dict[str, object] = {
    "active_gigachat_model": "GigaChat-2-Pro",
    "gigachat_context_ratio": 0.10,
    "gigachat_max_output_tokens": 2048,
    "embedding_context_ratio": 0.25,
    "rag_top_k": 6,
    "operator_escalation_threshold": 0.80,
}

DEFAULT_PROMPTS: dict[PromptType, str] = {
    PromptType.USER_SUPPORT: (
        "Ты AI-специалист технической поддержки 1С. Используй только факты из "
        "контекста обращения и KNOWLEDGE EVIDENCE. Давай конкретные пошаговые "
        "действия, ссылайся на источники как [S1], [S2]. Не придумывай пункты "
        "меню, версии и причины ошибок. Если данных недостаточно, снижай confidence. "
        "Если пользователь явно просит оператора, confidence должен быть равен 0."
    ),
    PromptType.OPERATOR_GIGACHAT: (
        "Ты AI-помощник оператора технической поддержки 1С. На основании последних "
        "сообщений диалога, вложений и KNOWLEDGE EVIDENCE подготовь точный "
        "редактируемый шаблон ответа клиенту. Обращайся к клиенту напрямую, не "
        "добавляй служебные комментарии или метку «шаблон». Не отправляй ответ "
        "пользователю и не придумывай отсутствующие факты."
    ),
    PromptType.KNOWLEDGE_CARD: (
        "Ты редактор базы знаний по 1С. На основании полного закрытого тикета, "
        "сообщений клиента и ответа поддержки заполни все поля карточки "
        "решённого случая. Выдели проверяемую проблему, симптомы, контекст, "
        "решение и результат. Не придумывай факты, версии и пункты меню: если "
        "решение не зафиксировано, честно укажи это в соответствующем поле."
    ),
}


async def seed_defaults(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(712031042)"))

        users = (
            (DEMO_USER_ID, UserRole.USER, "Демо пользователь"),
            (DEMO_OPERATOR_ID, UserRole.OPERATOR, "Демо оператор"),
            (DEMO_ADMIN_ID, UserRole.ADMIN, "Демо администратор"),
        )
        for user_id, role, display_name in users:
            if await session.get(User, user_id) is None:
                session.add(User(id=user_id, role=role, display_name=display_name))

        sections = (
            (DOCUMENTATION_SECTION_ID, "Документация 1С"),
            (DEFAULT_CASE_SECTION_ID, "Журнал обращений"),
            (INTERNAL_KB_SECTION_ID, "Внутренняя база знаний"),
        )
        for section_id, name in sections:
            if await session.get(KnowledgeSection, section_id) is None:
                session.add(KnowledgeSection(id=section_id, name=name, is_enabled=True))

        await session.flush()

        for prompt_type, content in DEFAULT_PROMPTS.items():
            active = await session.scalar(
                select(SystemPrompt).where(
                    SystemPrompt.type == prompt_type,
                    SystemPrompt.is_active.is_(True),
                )
            )
            if active is None:
                last_version = await session.scalar(
                    select(func.max(SystemPrompt.version)).where(
                        SystemPrompt.type == prompt_type
                    )
                )
                session.add(
                    SystemPrompt(
                        type=prompt_type,
                        content=content,
                        is_active=True,
                        version=(last_version or 0) + 1,
                        updated_by=DEMO_ADMIN_ID,
                    )
                )

        for key, value in DEFAULT_SETTINGS.items():
            if await session.get(SystemSetting, key) is None:
                session.add(SystemSetting(key=key, value=value))

        await session.commit()
