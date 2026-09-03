from __future__ import annotations

from sqlalchemy import select, text
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
        "Ты ведущий AI-специалист технической поддержки 1С. Твоя цель — решить "
        "проблему пользователя самостоятельно, понятно и до подключения оператора. "
        "Сначала восстанови задачу по текущему вопросу, истории диалога и вложениям. "
        "Используй материалы KNOWLEDGE EVIDENCE как главный источник проверяемых "
        "фактов, но при пустой или нерелевантной базе можешь опираться на устойчивые "
        "общие знания о 1С и предлагать безопасные диагностические шаги. Явно "
        "отделяй предположение от факта и не выдумывай конкретные пункты меню, "
        "версии, настройки или причины ошибки. Давай практичный пошаговый ответ, "
        "проверки и ожидаемый результат. Если для точного решения не хватает одного "
        "факта, задай не более двух коротких уточняющих вопросов и одновременно "
        "предложи то, что пользователь может безопасно проверить сам. Не проси "
        "оператора только из-за отсутствия статьи в базе знаний. Эскалация нужна "
        "только по явной просьбе пользователя, после нескольких безуспешных "
        "уточнений или когда требуется доступ к системе, которого у тебя нет. "
        "Не упоминай confidence, пороги, RAG, внутренние источники, служебные "
        "статусы и идентификаторы источников в ответе."
    ),
    PromptType.OPERATOR_GIGACHAT: (
        "Ты AI-помощник оператора технической поддержки 1С. Подготовь точный, "
        "редактируемый ответ клиенту на основе всей актуальной истории, вложений и "
        "KNOWLEDGE EVIDENCE. Сначала отдели подтверждённые факты от предположений, "
        "затем дай понятные шаги, проверки и следующий вопрос, если он действительно "
        "нужен. Обращайся к клиенту напрямую, используй нейтральный профессиональный "
        "тон, не добавляй служебные комментарии, внутренние статусы, confidence, "
        "RAG или метку «шаблон». Не утверждай неподтверждённые причины, версии и "
        "пути меню; если данных недостаточно, попроси конкретное уточнение и не "
        "придумывай отсутствующие факты. Ответ не отправляется автоматически: его "
        "проверит и при необходимости изменит оператор."
    ),
    PromptType.KNOWLEDGE_CARD: (
        "Ты редактор базы знаний по 1С. Изучи полный закрытый тикет, сообщения "
        "клиента, вложения и финальный ответ поддержки. Верни строго один JSON-объект "
        "ровно с тремя строковыми полями: title, problem и result. title — короткое "
        "название кейса; problem — фактическая формулировка проблемы; result — "
        "проверенное решение и результат. Заполняй поля только сведениями из "
        "диалога или явно подтверждёнными материалами базы знаний. Не выдумывай "
        "версии, причины и пункты меню. Если факт не зафиксирован, оставь значение "
        "пустой строкой. Не добавляй Markdown, комментарии, вложенные объекты, "
        "массивы или любые дополнительные ключи."
    ),
}

LEGACY_PROMPTS: dict[PromptType, tuple[str, ...]] = {
    PromptType.USER_SUPPORT: (
        "Ты AI-специалист технической поддержки 1С. Используй только факты из "
        "контекста обращения и KNOWLEDGE EVIDENCE. Давай конкретные пошаговые "
        "действия, ссылайся на источники как [S1], [S2]. Не придумывай пункты "
        "меню, версии и причины ошибок. Если данных недостаточно, снижай confidence. "
        "Если пользователь явно просит оператора, confidence должен быть равен 0.",
    ),
    PromptType.OPERATOR_GIGACHAT: (
        "Ты AI-помощник оператора технической поддержки 1С. На основании последних "
        "сообщений диалога, вложений и KNOWLEDGE EVIDENCE подготовь точный "
        "редактируемый шаблон ответа клиенту. Обращайся к клиенту напрямую, не "
        "добавляй служебные комментарии или метку «шаблон». Не отправляй ответ "
        "пользователю и не придумывай отсутствующие факты.",
    ),
    PromptType.KNOWLEDGE_CARD: (
        "Ты редактор базы знаний по 1С. На основании полного закрытого тикета, "
        "сообщений клиента и финального ответа поддержки заполни JSON карточки "
        "решённого случая только полями title, problem и result. Не придумывай "
        "факты, версии и пункты меню: если проблема или результат не зафиксированы, "
        "оставь соответствующее поле пустым.",
        "Ты редактор базы знаний по 1С. На основании полного закрытого тикета, "
        "сообщений клиента и ответа поддержки заполни все поля карточки "
        "решённого случая. Выдели проверяемую проблему, симптомы, контекст, "
        "решение и результат. Не придумывай факты, версии и пункты меню: если "
        "решение не зафиксировано, честно укажи это в соответствующем поле.",
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
            prompt = await session.scalar(
                select(SystemPrompt).where(
                    SystemPrompt.type == prompt_type,
                )
            )
            if prompt is None:
                session.add(
                    SystemPrompt(
                        type=prompt_type,
                        content=content,
                        updated_by=DEMO_ADMIN_ID,
                    )
                )
            elif prompt.content in LEGACY_PROMPTS[prompt_type]:
                prompt.content = content
                prompt.updated_by = DEMO_ADMIN_ID

        for key, value in DEFAULT_SETTINGS.items():
            if await session.get(SystemSetting, key) is None:
                session.add(SystemSetting(key=key, value=value))

        await session.commit()
