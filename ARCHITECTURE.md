# Архитектура AI-агента техподдержки 1С

> Единый архитектурный контракт проекта: backend, RAG/GigaChat pipeline и три frontend-панели `user / operator / admin`.

## Оглавление

### Часть I — Общая архитектура

1. TL;DR
2. Контекст, цели и требования
3. Архитектурные решения
4. Высокоуровневая архитектура
5. Технологический стек и LangChain-first
6. Нефункциональные требования
7. Метрики эффективности
8. MVP и Roadmap
9. Риски

### Часть II — Backend

10. Границы backend
11. Lifecycle тикета
12. RAG
13. GigaChat + LangChain/GigaChain
14. Скриншоты и runtime attachments
15. Внешние каналы Bitrix24/Redmine
16. Модель данных
17. Что сознательно не усложняем

### Часть III — Frontend

18. Общая frontend-архитектура
19. SSE и взаимодействие с backend
20. Backend API contract для frontend
21. User panel
22. Operator panel
23. Admin panel
24. Admin — Knowledge Base
25. Admin — System Prompts
26. Admin — AI Settings
27. Admin — Monitoring
28. Frontend project structure
29. Frontend performance / correctness
30. Frontend security

### Часть IV — План разработки и справка

31. Вертикальные срезы разработки
32. Структура репозитория
33. Источники

# Часть I — Общая архитектура

## 1. TL;DR

- **Фронтенд собственный** (не 1С/Bitrix24 UI): одно SPA с тремя панелями — `user`, `operator`, `admin`. Backend остаётся channel-agnostic, поэтому Bitrix24/Redmine позже подключаются через адаптеры без переписывания ядра.
- **Backend — модульный монолит на FastAPI**, не микросервисы: меньше DevOps-расходов на хакатон, модули (RAG, Vision, Escalation, KB) изолированы и готовы к выносу в отдельные сервисы позже.
- **GigaChat — центральная генеративная модель:** используем API для формирования финального ответа и анализа приложенных скриншотов. Для MVP основной кандидат — `GigaChat (активная модель)`.
- **Embeddings делаем локально:** Freemium предоставляет бесплатные токены генерации, но векторное представление текста оплачивается отдельно. Поэтому retrieval не зависит от платного Embeddings API; основной локальный кандидат — `BAAI/bge-m3`.
- **Критичное ограничение Freemium — 1 поток генерации.** Все GigaChat generation, vision и Files API операции проходят через единый re-entrant `GenerationGate` внутри процесса. Обычный пользовательский turn использует два последовательных GigaChat generation-call с одним `GenerationContext`: structured `confidence` и streaming user answer. При screenshot его parse выполняется до retrieval в том же атомарном turn. Confidence публикуется скрытым от пользователя SSE-событием; при достаточном значении запускается streaming answer, при низком выполняется существующая clarification/escalation policy без второго call. Ручной шаблон оператора выполняется отдельным generation-call.
- **GigaChain используем точечно**, где он ускоряет интеграцию с GigaChat/LangChain, но не строим многошаговую agent-chain, которая последовательно занимает единственный поток.

## 2. Контекст, цели и требования

### Заказчик и бизнес-цели

Компания: **АО «Молвест»**. Цель — AI-агент для автоматизации техподдержки пользователей 1С.

| Бизнес-цель                      | Целевой показатель             |
| -------------------------------- | ------------------------------ |
| Снизить нагрузку на техподдержку | −30–40% обращений к операторам |
| Сократить время ожидания         | <5 сек на генерацию ответа     |
| Единообразие ответов             | централизованная база знаний   |
| Круглосуточная поддержка         | без участия человека           |

### Функциональные сценарии и приоритет реализации

| #   | Сценарий                                            | Статус на хакатон                                            | Ключевая механика                                                                                                                                                                                     |
| --- | --------------------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Вопрос–ответ (чат-бот)**                          | **Обязательный MVP**                                         | Пользователь пишет вопрос в нашем веб-чате → backend анализирует запрос → выполняет поиск по БЗ → GigaChat формирует понятный ответ → при низкой уверенности обращение эскалируется оператору         |
| 2   | **Автоматическое подключение к существующему чату** | **Roadmap, не MVP**                                          | В будущем агент подключается к Bitrix24/Redmine, читает сообщения в реальном времени и либо предлагает оператору черновик, либо отвечает автоматически по настройке                                   |
| 3   | **Анализ изображений и скриншотов**                 | **Обязательный MVP, доступен в каждом диалоге по умолчанию** | В любом чате пользователь может приложить PNG/JPEG-скриншот 1С; агент извлекает текст и визуальные признаки, определяет ошибку/поле/состояние интерфейса и использует результат как часть RAG-запроса |
| 4   | **Управление базой знаний**                         | **Обязательный MVP**                                         | Администратор создаёт/редактирует/удаляет разделы БЗ, загружает документы, запускает переиндексацию, обновляет источники и управляет параметрами системы                                              |

#### 1.2.1 Текущий канал взаимодействия и совместимость с Bitrix24/Redmine

На хакатоне **основным интерфейсом является собственный frontend**, потому что так быстрее реализовать и качественно продемонстрировать основной пользовательский сценарий.

При этом backend проектируется **channel-agnostic**: бизнес-логика не зависит от UI. Входящее сообщение нормализуется в единый контракт `IncomingMessage`, а ответ — в `OutgoingMessage`.

- сейчас источником сообщений является наш веб-frontend;
- позже Bitrix24 и Redmine подключаются через адаптеры без изменения RAG, Vision, Dialog и Escalation-логики;
- REST/SSE API backend остаётся единым ядром системы;
- особенности конкретного канала изолируются в `IChannelAdapter`.

Цель: после хакатона интеграция с Bitrix24/Redmine должна быть **подключением нового интерфейсного адаптера, а не переписыванием backend**.

#### 1.2.2 Эскалация и настраиваемый порог уверенности

    Если confidence ниже порога, второй user-answer call не запускается: backend либо
    задаёт детерминированный уточняющий вопрос (не более двух раундов), либо переводит
    обращение оператору.

Порог уверенности:

- хранится как системная настройка;
- по умолчанию — **80%**;
- настраивается в админ-панели;
- изменение порога не требует перезапуска приложения.

Отдельного `escalation_reason` в MVP нет.

Причина эскалации восстанавливается из персистентного system-сообщения, которое backend создаёт в момент перехода:

```text
Message.author_type = system
Message.text = "К обращению подключился специалист поддержки."
Message.confidence = <confidence текущего turn>
Message.sources = <internal snapshot RAG evidence>
```

Таким образом backend сохраняет значение confidence и внутренний source snapshot,
на основании которых был принят routing decision, без отдельной сущности/поля
причины эскалации. Текущий `MessageDto` не включает `sources`, поэтому frontend и
текущий admin UI эти snapshots не показывают.

### Источники данных и структура базы знаний

База знаний должна быть **секционной и расширяемой**: администратор может добавлять и удалять логические разделы без изменения кода.

Минимальные разделы:

1. **Документация 1С**

- официальная документация по платформе;
- типовые конфигурации;
- руководства пользователя;
- руководства администратора.

2. **Журнал обращений**

- успешно решённые инциденты;
- неуспешно решённые инциденты;
- запросы пользователей и итоговые решения;
- статус решения хранится в метаданных.

3. **Внутренняя база знаний техподдержки АО «Молвест»**

- инструкции;
- регламенты;
- внутренние руководства;
- памятки и типовые решения.

Поддерживаемые форматы исходных документов: **Word, PDF, HTML, Markdown**.

Изображения и скриншоты пользователей являются runtime-источником контекста: извлечённый из них текст и визуальное описание участвуют в поиске по БЗ и генерации ответа.

Загрузка реальной документации 1С остаётся отдельным roadmap-шагом и не выполняется
автоматически при startup. В MVP документы загружаются администратором через KB API;
seed не скачивает внешний массив документов.

## 3. Архитектурные решения (ADR)

### ADR-1 · Собственный фронтенд сейчас, Bitrix24/Redmine через адаптеры позже

- **Контекст:** ТЗ предполагает Bitrix24 и Redmine HelpDesk, но на хакатоне важнее быстро довести основной пользовательский сценарий до стабильного состояния.
- **Решение:** на MVP строим одно SPA с тремя role-зонами — пользователь, оператор и администратор. Backend сразу проектируем независимо от интерфейса, а Bitrix24/Redmine подключаем позднее через `IChannelAdapter`.
- **Почему:** собственный frontend ускоряет разработку и позволяет качественно проработать UX. Единые backend-контракты гарантируют, что позднее интеграция каналов не потребует переписывать RAG/Vision/KB-ядро.
- **Важно для MVP:** автоматическое подключение к существующему чату не реализуем как обязательный сценарий первого этапа — оно остаётся в Roadmap.
- **Отклонённая альтернатива:** начинать с виджета внутри Bitrix24/Open Lines — повышает интеграционные риски и отвлекает от критериев «работоспособность прототипа», «GigaChat» и «UX».

### ADR-2 · Модульный монолит вместо микросервисов

- **Решение:** один backend-сервис (FastAPI) с модулями `dialog`, `rag`, `vision`, `escalation`, `kb`, а не отдельные микросервисы.
- **Почему:** на хакатоне важнее скорость разработки и деплоя, чем изоляция; границы модулей спроектированы так, чтобы `rag`/`vision` можно было вынести в отдельные сервисы при росте нагрузки (они самые GPU/latency-чувствительные).

### ADR-3 · GigaChat как основная интеллектуальная модель + локальные embeddings

- **GigaChat используется в основном пользовательском сценарии:** отдельным structured-вызовом анализирует приложенный screenshot до retrieval, затем в одном `GenerationContext` выполняет structured confidence call и, если threshold пройден, streaming user-answer call. Загруженные file ID переиспользуются в обоих вызовах; технический confidence prompt захардкожен в backend и не является `SystemPrompt`. Конкретная модель GigaChat и runtime-бюджеты выбираются администратором из валидируемых настроек.
- **Embeddings API GigaChat в MVP не используем:** он оплачивается отдельно от Freemium-генерации, поэтому retrieval должен работать полностью локально и не зависеть от платной услуги.
- **Единственная embedding-модель MVP:** `BAAI/bge-m3`.
- **Почему `BGE-M3`:** мультиязычность (>100 языков), 1024-мерные dense-вектора, контекст до 8192 токенов, MIT-лицензия и возможность получать dense + sparse representations для hybrid retrieval.
- **Runtime BGE-M3:** зафиксированный snapshot модели скачивается на этапе сборки backend-образа, загружается через `BGEM3FlagModel` в FastAPI lifespan и прогревается до readiness. Во время обработки запросов сеть для Hugging Face не используется.
- **Runtime Docling:** layout, TableFormer и EasyOCR artifacts скачиваются на этапе сборки backend-образа в `/opt/models/docling`, передаются в `DocumentConverter` через `DOCLING_ARTIFACTS_PATH` и прогреваются в FastAPI lifespan. Во время ingestion сеть для Hugging Face и EasyOCR не используется.
- **Интерфейсы разделяем:** `GigaChatProvider` отвечает за generation/multimodal input, `EmbeddingProvider` — за локальную векторизацию. Это не смешивает платёжные/сетевые ограничения GigaChat с индексом БЗ.
- **Ограничение Freemium:** один поток generation-запросов. Единый re-entrant `GenerationGate` находится в `app/core/generation_gate.py`; provider защищает каждый GigaChat/file/vision вызов, а сервис удерживает тот же gate на всём атомарном user turn. Дополнительно `TurnCoordinator` защищает admission внутри процесса, а PostgreSQL `pg_advisory_xact_lock(712031043)` и проверка `pending/processing` user triggers не допускают параллельные AI user turns между workers. Embeddings/retrieval выполняются локально.
- **Не делаем в MVP:** self-hosted генеративную LLM и альтернативные embedding-модели «на всякий случай». Если BGE-M3 не проходит наш golden dataset, модель меняется через `EmbeddingProvider`, но до измерений не усложняем архитектуру.

### ADR-4 · Qdrant + единая коллекция знаний

- **Решение:** Qdrant как поисковый индекс.
- **Основная коллекция:** `knowledge_chunks`.
- **Почему одна коллекция:** разделы БЗ должны динамически создаваться и удаляться из админки. Раздел — это metadata/payload (`section_id`), а не отдельная физическая коллекция.
- **Payload каждого чанка:** `document_id`, `section_id`, `title`, `source_type`, `one_c_version`, `tags`, `heading_path`, `page`, `chunk_index`, `is_enabled`, `updated_at`, `answer_eligible` и технические metadata для отображения источника.
- **Поиск:** hybrid retrieval — dense semantic search с preflight threshold `0.35` + sparse/lexical search; Qdrant объединяет результаты через RRF, затем `RAGService` делает rank fusion между prompt/screenshot queries.
- **Неуспешные обращения:** остаются в истории/аналитике и не публикуются как документы основной БЗ без административного approve.

### ADR-5 · Схема PostgreSQL создаётся из актуальных моделей

- **Решение:** backend безусловно создаёт схему через `Base.metadata.create_all`
  во время startup lifespan. Начальные пользователи, разделы БЗ, настройки и все
  три системных prompt добавляются через seed.
- **Миграции базы данных не используются:** в репозитории нет Alembic и других
  migration-скриптов, а контейнеры запускают сразу Uvicorn.
- **Почему:** для MVP нужен один воспроизводимый initial state при сборке и
  запуске без отдельного шага миграций и рассинхронизации модели с базой.
- **Правило изменения схемы:** изменения ORM-моделей сначала отражаются в
  `backend/app/models`, после чего для среды с изменившимся контрактом
  пересоздаётся PostgreSQL volume. Создание схемы идемпотентно для уже
  существующего актуального volume.
- **Конфигурация Docker:** runtime-переменные хранятся в единственном корневом
  `.env`; оба Compose-файла передают его backend через `env_file`, а
  Docker-specific hostnames, ports и TLS paths задаются только в Compose.

### 3.1. Текущее состояние реализации

Следующие правила уже реализованы в backend и являются частью текущего MVP-контракта:

- все generation, vision и Files API вызовы GigaChat сериализуются единым
  re-entrant `GenerationGate` внутри процесса; сервисы могут удерживать его на всём
  атомарном turn, а provider дополнительно защищает отдельные вызовы;
- пользовательский AI-turn глобально допускается только один: `TurnCoordinator`
  дополняется PostgreSQL advisory transaction lock с ключом `712031043` и проверкой
  persisted `pending/processing` triggers, поэтому блокировка действует между
  backend workers; это не распределённая блокировка всех generation-вызовов;
- при закрытии любого Dialog в той же транзакции создаётся один pending
  `KnowledgeCandidate` с детерминированной начальной карточкой; старые закрытые
  Dialog backfill-ятся при старте приложения;
- `DialogFeedback` хранится независимо от candidate и допускает `helpful`,
  `ai_error` либо отсутствие оценки (`unrated`);
- approve/reject/hard-delete блокируют Dialog и candidate в одном порядке и
  удерживают блокировки до commit или компенсации внешних операций;
- после restart восстанавливаются user turns со статусом `processing`, а документы
  `uploaded/processing` снова ставятся в ingestion; в RAG участвуют только
  документы со статусом `indexed`, включённые секция и документ;
- BGE-M3 и Docling PDF pipeline прогреваются до readiness; runtime image содержит
  все необходимые model artifacts и не скачивает модели во время обработки запроса;
- operator Dialog SSE публикует `operator_access_revoked` после назначения тикета
  другому оператору и закрывает доступ к дальнейшим событиям;
- `MetricEvent` хранит один aggregate на `user_turn`: полную latency цепочки,
  success/error, confidence, модель, snapshot user-support prompt,
  retrieval-настройки и суммарный usage confidence/answer calls; RAG source snapshot
  сохраняется во внутреннем поле `Message.sources`, но не отдаётся через текущий
  `MessageDto`;
- admin settings позволяют одной atomic mutation менять `active_model`, оба context
  ratios, `gigachat_max_output_tokens`, `rag_top_k` и
  `operator_escalation_threshold`; backend валидирует модель, диапазоны и общий
  GigaChat budget;
- фоновый sweeper каждые `DIALOG_IDLE_SCAN_SECONDS` закрывает неактивные Dialog в
  режиме `ai_support` после `DIALOG_IDLE_TIMEOUT_HOURS` без новых user/assistant
  сообщений; такие тикеты остаются `unrated` и отображаются как решённые AI.
- demo-auth/seed-пользователи остаются намеренным MVP-режимом для демонстрации и не
  являются текущей P0-задачей; production identity provider — отдельный roadmap.

В этой версии `knowledge_card` prompt остаётся для явного legacy/admin backfill;
обычный candidate создаётся без дополнительного LLM-вызова и редактируется
администратором перед approve. Approve идемпотентен для повторной попытки после
сбоя: deterministic document key переиспользуется, уже индексированный документ
повторно не ingest-ится, а candidate становится approved только после успешной
индексации и commit.

## 4. Высокоуровневая архитектура

```mermaid
flowchart TB
    subgraph CLIENT["Vite SPA: три role-зоны"]
        FE["User panel"]
        OP["Operator panel"]
        ADMIN["Admin panel"]
    end

    subgraph GW["API Gateway (FastAPI)"]
        API["REST + SSE"]
    end

    subgraph CORE["Ядро приложения"]
        DIALOG["Dialog Service"]
        RAG["RAG Engine"]
        VISION["Vision / Attachments Handler"]
        ESCALATION["Escalation Service"]
        KB["KB Service"]
    end

    subgraph AI["AI-провайдеры"]
        GIGA["GigaChatProvider<br/>Generate + Vision"]
        EMB["Local EmbeddingProvider<br/>BAAI/bge-m3"]
    end

    subgraph DATA["Хранилища"]
        PG[("PostgreSQL")]
        VDB[("Qdrant")]
        S3[("MinIO / local storage")]
    end

    subgraph EXT["Внешние каналы (Roadmap)"]
        BITRIX["Bitrix24 Open Lines"]
        REDMINE["Redmine HelpDesk"]
    end

    FE --> API
    OP --> API
    ADMIN --> API
    API --> DIALOG
    DIALOG --> RAG
    DIALOG --> VISION
    DIALOG --> ESCALATION

    VISION --> RAG
    RAG --> EMB
    EMB --> VDB
    RAG --> VDB
    RAG --> GIGA

    KB --> EMB
    KB --> VDB
    KB --> PG

    DIALOG --> PG
    ESCALATION --> PG
    VISION --> S3

    API -.->|adapter, roadmap| BITRIX
    API -.->|adapter, roadmap| REDMINE
```

**Компоненты:**

- **Frontend** — на MVP: чат пользователя, панель оператора и админ-панель в одном Vite + React + TypeScript SPA. Возможность прикрепить скриншот присутствует в каждом диалоге по умолчанию. панель оператора с AI GigaChat входит в MVP; Roadmap относится только к внешним Bitrix24/Redmine.
- **API Gateway** — FastAPI, REST для команд/сообщений + SSE для streaming и событий состояния; те же контракты позже используются интеграционными адаптерами.
- **Dialog Service** — состояние диалога/история, роутинг в RAG/Vision/Escalation.
        - **RAG Engine** — локальная векторизация (`EmbeddingProvider`) → hybrid retrieval из Qdrant → evidence для единого user `GenerationContext`.
        - **Vision / Attachments Handler** — хранит runtime attachment, для screenshot выполняет отдельный GigaChat parse (`extracted_text + visual_summary`) до RAG, затем переиспользует тот же `file_id` в confidence и answer calls. Text attachments также передаются в generation-вызовы с `function_call="auto"`.
        - **Dialog decision flow** — `DialogService` один раз собирает `GenerationContext`, вызывает hardcoded confidence assessment, сравнивает его с `operator_escalation_threshold` и запускает streaming answer либо существующую clarification/escalation policy.
  - **Moderation flow** — `ModerationService` показывает администратору завершённые тикеты с `DialogFeedback.verdict=ai_error`, управляет candidate и выполняет подтверждённое каскадное удаление разобранных ошибочных чатов.
- **KB Service** — CRUD документов, чанкинг, (ре)индексация.
- **Channel Adapters** (roadmap) — Bitrix24 Open Lines и Redmine HelpDesk через `IChannelAdapter`. Адаптер преобразует сообщения конкретной платформы в единый внутренний контракт backend и обратно.

## 5. Технологический стек и LangChain-first

| Слой                | Технология                                                                  | Почему                                                                                                                                  |
| ------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend            | **React 18 + TypeScript + Vite + Tailwind + React Router v7 + React Query** | Один SPA для user/operator/admin; Router — маршрутизация, React Query — server state, Tailwind — UI                                     |
| Realtime            | **SSE + REST**                                                              | REST отправляет команды/сообщения; SSE доставляет токены GigaChat и события состояния тикета                                            |
| Backend             | Python 3.11 + FastAPI (async)                                               | REST/SSE API, приём сообщений и файлов                                                                                                  |
| Каналы              | `IChannelAdapter` + REST/webhooks                                           | MVP — собственный frontend; Bitrix24/Redmine адаптеры остаются Roadmap, но backend-контракт уже совместим                               |
| Генерация + Vision  | GigaChat API: Lite / Pro / Max / Ultra через `langchain-gigachat`           | Активная модель задаётся backend-политикой и отображается в админке; единый `GigaChatProvider` скрывает различия моделей от RAG/backend |
| Embeddings          | **Локально `BAAI/bge-m3`** через `FlagEmbedding` / `sentence-transformers`  | Бесплатно локально; RU/multilingual; dense+sparse representations для hybrid retrieval                                                  |
| Оркестрация         | LangChain Core / LCEL + `langchain-gigachat`                                | Простые последовательные/параллельные Runnable-цепочки без agent executor; прозрачный контроль latency и числа GigaChat-вызовов         |
| Векторная БД        | Qdrant                                                                      | Hybrid search, payload-фильтры, Docker-friendly                                                                                         |
| РСУБД               | PostgreSQL                                                                  | Диалоги, тикеты, метаданные БЗ, логи, метрики                                                                                           |
| Фоновые задачи      | FastAPI `BackgroundTasks` / простой in-process worker                       | Для MVP достаточно для переиндексации небольшого объёма документов без отдельной очереди                                                |
| Объектное хранилище | MinIO (S3-совместимо)                                                       | Скриншоты, исходные документы                                                                                                           | Быстро извлекает текст/коды ошибки локально перед retrieval; GigaChat всё равно получает исходное изображение и выполняет смысловой Vision-анализ |
| Наблюдаемость       | Application logs + базовые метрики backend                                  | Latency, ошибки, confidence, источники ответа и эскалации без внешнего SaaS                                                             |
| Проверка RAG        | `tests/rag/evaluate_rag.py` + `tests/rag/rag_golden.json`                   | Скрипт прогоняет тестовые вопросы через retrieval и показывает, попал ли ожидаемый источник в top-k                                     |
| Деплой              | Docker Compose (демо) → Kubernetes (прод)                                   | Скорость на хакатоне, понятный путь роста                                                                                               |

### LangChain-first правило разработки

Для MVP **вся интеграция с GigaChat сначала реализуется средствами `langchain-gigachat` и LangChain Core**.

Прямые HTTP-вызовы GigaChat API и прямое использование Python SDK `gigachat` в сервисах запрещены, если та же возможность уже присутствует в `langchain-gigachat`.

Это относится к:

- generation;
- async generation;
- streaming;
- structured output;
- multimodal messages;
- upload/delete runtime-файлов;
- model parameters;
- retries;
- tracing metadata.

Исключение — только отсутствующая в wrapper-е возможность, изолированная внутри `GigaChatProvider`.

## 6. Нефункциональные требования

**Латентность (бюджет на <5 сек из ТЗ):**

| Этап                       | Бюджет                                                                  |
| -------------------------- | ----------------------------------------------------------------------- |
| Local BGE-M3 embedding     | измеряем на целевом железе                                              |
| Поиск в Qdrant             | целевой порядок десятки миллисекунд                                     |
    | GigaChat до первого токена | измеряем на API; user UI получает первый answer chunk сразу через SSE после скрытого confidence call |
| End-to-end                 | целевой KPI заказчика <5 с; обязательно подтвердить экспериментально    |

_Открытый вопрос для приёмки: считать SLA «<5 сек» как время до первого токена (со стримингом) или до полного ответа — уточнить у В.В. Донцовой._

**Безопасность и данные:** self-hosted Qdrant/хранилище/Postgres; JWT + роли user/operator/admin. GigaChat credentials находятся только на backend. В Docker/Linux устанавливаем доверенный сертификат НУЦ Минцифры или задаём `ca_bundle_file`; SSL verification не отключаем. Runtime-файлы после использования удаляются из GigaChat File Storage. PII не пишем в технические логи без необходимости.

**Масштабирование:** на MVP отдельная очередь задач не нужна. Индексация запускается через FastAPI `BackgroundTasks` / простой worker, а документы в `uploaded/processing` восстанавливаются при старте. Один пользовательский AI-turn глобально защищён PostgreSQL advisory admission lock, а локальный `TurnCoordinator` добавляет process-local guard. `GenerationGate` сериализует provider work только внутри одного процесса; распределённая очередь для всех generation/file/vision вызовов при нескольких replicas остаётся Roadmap.

## 7. Метрики эффективности

| Метрика                      | Как считаем                                                                           | Целевой показатель                                    |
| ---------------------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| % обработанных без эскалации | count(escalated=false) / total                                                        | Снижение обращений к операторам на 30–40%             |
| Среднее время ответа         | `MetricEvent.latency_ms` для полного user turn: от начала обработки persisted message до answer/clarification/escalation/error; агрегаты p50/p95 | <5 сек                                                |
| Количество эскалаций         | count(escalated=true) / период                                                        | Тренд к снижению                                      |
| Проверка retrieval           | `tests/rag/evaluate_rag.py`: сколько golden-вопросов нашли ожидаемый источник в top-3 | Используем как внутреннюю проверку при изменениях RAG |

`MetricEvent.event_type` различает `user_turn`, `operator_template` и
`knowledge_card`; monitoring KPI агрегирует только `user_turn`, чтобы ручные
шаблоны и служебный backfill не искажали пользовательские показатели. Ошибки
обработки считаются по `success=false`.

Один `user_turn` начинается, когда backend принимает persisted user message в
обработку, и завершается после полного `assistant_done`, решения clarification /
escalation или ошибки. Поэтому `latency_ms`, среднее время и p50/p95 включают всю
цепочку `screenshot parse + RAG + confidence + answer stream`, а не отдельный
GigaChat call. В этот же `MetricEvent` складываются `prompt_tokens`,
`completion_tokens` и `precached_prompt_tokens` confidence и answer calls; если
answer не запускался, сохраняется usage только confidence call.

## 8. MVP и Production Roadmap

| Функция ТЗ             | Хакатон (MVP)                                                                                                                    | Прод (Roadmap)                                                               |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Q&A чат-бот            | **Свой веб-чат + RAG на GigaChat API**                                                                                           | Bitrix24 Open Lines и Redmine HelpDesk через адаптеры                        |
| Совместимость каналов  | Единые backend-контракты `IncomingMessage/OutgoingMessage`, channel-agnostic ядро                                                | Реальные webhooks/API конкретных платформ                                    |
| Автоподключение к чату | **Не реализуем как обязательный MVP**                                                                                            | Listener Bitrix24/Redmine + режимы `suggest/auto`                            |
| База знаний            | **Секции + CRUD документов + human-in-the-loop candidate approval + индексация**                                                 | Версионирование, массовый импорт                                             |
| Минимальные данные     | Документы загружаются через KB API; автоматический seed реальной документации 1С не выполняется                                  | Полный массив источников заказчика и автоматическая стартовая загрузка       |
| Админ-настройки        | **Модель, context ratios, max output tokens, `rag_top_k` и `operator_escalation_threshold`** редактируются одной atomic mutation | Продвинутые политики эскалации, RBAC, SLA                                    |
| Метрики                | % успешных ответов, среднее время ответа, число эскалаций                                                                        | Prometheus/Grafana, алерты, расширенная аналитика                            |
| Очереди/фоновые задачи | FastAPI `BackgroundTasks` / простой worker                                                                                       | Redis + Celery/RQ при росте объёма индексации и параллельных задач           |
| Контекст моделей       | GigaChat/BGE-M3 ratios, max output tokens и `rag_top_k` задаются через admin settings; история сообщений обрезается первой       | Более сложная memory/summarization логика только при измеримой необходимости |

### Проверка ожидаемого результата по ТЗ

| Требование заказчика  | Как закрываем                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------ |
| Работающий AI-агент   | Собственный web-чат на MVP; backend сразу совместим с будущими Bitrix24/Redmine-адаптерами |
| БЗ по продуктам 1С    | Обязательный раздел «Документация 1С», индексируемый в Qdrant                              |
| Анализ скриншотов     | Встроен в каждый диалог, GigaChat Vision → извлечённый контекст → RAG                      |
| Админ-панель          | Управление разделами/документами, ползунок confidence, мониторинг и логи                   |
| Обновление знаний     | Загрузка новых документов и переиндексация; закрытые кейсы как кандидаты в БЗ              |
| Документация          | `ARCHITECTURE.md`, Swagger UI `/docs` и ReDoc `/redoc`                                     |
| Метрики эффективности | % без эскалации, среднее время ответа, количество эскалаций, confidence                    |

## 9. Риски и митигации

### Последовательные confidence/answer calls: latency и gate

Новый runtime использует два последовательных GigaChat-call для обычного AI-turn и
переиспользует один собранный контекст:

```text
GenerationContext → structured confidence → threshold → streaming user answer
```

Confidence-событие отправляется в user-safe SSE без технического prompt. Если порог
пройден, первый chunk второго call сразу отправляется в SSE; backend не буферизует
ответ целиком. При низком confidence второй call не выполняется.

- confidence возвращает маленький structured `ConfidenceAssessment`;
- confidence использует отдельный hardcoded backend prompt и `max_tokens=64`;
- тот же `X-Session-ID` и неизменный базовый контекст позволяют переиспользовать
  совпадающий prompt-prefix;
- `GenerationGate` удерживается от screenshot/context preparation до конца
  confidence/answer sequence, поэтому другой generation-call не вклинивается;
- latency `user_turn` включает screenshot, RAG, confidence, весь answer stream и
  финальное решение.

| Риск                                                  | Влияние                                | Митигация                                                                                                                                         |
| ----------------------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Нестабильное распознавание мелкого/рукописного текста | Ошибочная диагностика скриншота        | Vision + regex по кодам ошибок + запрос переснять крупнее                                                                                         |
| Нет доступа к реальному Bitrix24/Redmine на хакатоне  | Нельзя показать «настоящую» интеграцию | На MVP показываем собственный frontend; совместимость доказываем едиными контрактами и `IChannelAdapter`, реальную интеграцию оставляем в Roadmap |
| Долгая индексация полной БЗ 1С                        | Не успеть до дедлайна                  | На демо — ограниченный, но реальный срез БЗ (ключевые документы + история обращений)                                                              |

# Часть II — Backend

Backend — модульный монолит FastAPI. Он владеет состоянием тикета, сообщениями, RAG, GigaChat, confidence/escalation, файлами, модерацией и API для пользовательского, операторского и административного интерфейсов.

## 10. Границы backend

```text
FastAPI / channel adapters
        ↓
    DialogService
    ├── ContextBuilder
    ├── RAGService
    ├── GigaChatProvider
    ├── AttachmentService
    ├── EscalationService
    └── Feedback / Moderation
        ↓
PostgreSQL / Qdrant / file storage
```

Главный принцип: бизнес-логика не знает о raw GigaChat HTTP. Вся LLM-разработка идёт LangChain-first через `langchain-gigachat`, а низкоуровневый SDK остаётся внутри `GigaChatProvider`.

## 11. Lifecycle тикета: AI → оператор → модерация

### Сквозной сценарий поддержки: AI → оператор → обучение

Главный продуктовый сценарий — **один непрерывный тикет**, который может пройти два режима:

```text
1. AI самостоятельно общается с пользователем
2. При необходимости к тому же тикету подключается оператор
```

Пользователю не нужно создавать новое обращение или повторять проблему.

---

#### Этап 1. Пользователь общается с AI

Новый тикет создаётся в режиме:

```text
Dialog.mode = ai_support
Dialog.status = active
dialog_confidence = 1.0
```

Пользователь может в любом сообщении отправить:

- текст;
- screenshot PNG/JPEG;
- поддерживаемый документ/файл.

Вложения являются обычной частью сообщения и доступны во всех чатах по умолчанию.

Каждый новый turn работает по следующей общей логике:

```text
текущий вопрос
+ embedding sliding window
        ↓
    BGE-M3
        ↓
    Qdrant
        ↓
    rag_top_k evidence

    ONE GenerationContext
    + active user_support prompt for answer
    + current message
    + recent dialog context
    + RAG evidence
    + screenshot analysis
    + runtime attachments
            ↓
    GenerationGate.acquire()
            ↓
    CALL #1 — structured ConfidenceAssessment
    hardcoded confidence prompt + current escalation threshold
            ↓
    confidence event (hidden technical details)
    ├── confidence >= threshold → CALL #2 user answer, stream tokens through SSE
    └── confidence < threshold → no CALL #2; clarification or operator_support
```

Второй call использует тот же `GenerationContext` и только редактируемый
`SystemPrompt(type=user_support)`. Его текст не буферизуется: каждый очищенный
chunk сразу публикуется как `assistant_token`, затем полный ответ сохраняется и
завершается `assistant_done`. При явной просьбе оператора LLM pipeline обходится:
backend сразу выставляет confidence `0` и переводит Dialog в `operator_support`.

---

#### Этап 2A. AI решил проблему без оператора

Если задача решена, пользователь завершает обращение. В транзакции закрытия backend
создаёт один `KnowledgeCandidate` со статусом `pending`; затем пользователь видит:

```text
Решение помогло?

[ Да, помогло ]   [ Нет, AI ошибся ]
```

Если пользователь выбирает:

```text
Да, помогло
```

backend сохраняет итоговую оценку. Candidate уже был создан в транзакции закрытия;
idempotent get-or-create используется только как backfill для старых закрытых
тикетов:

```text
create_or_get_candidate(
    dialog_id = dialog.id,
    source = user_feedback,
)
```

Для новых закрытых тикетов кандидат уже создан при `close`. В БД действует:

```text
UNIQUE(KnowledgeCandidate.dialog_id)
```

Поэтому один Dialog физически не может создать два кандидата на модерацию.
Кандидат попадает в отдельную административную очередь / журнал закрытых обращений.

Администратор видит:

- полный завершённый диалог;
- вопрос пользователя;
- финальное решение;
- attachments/screenshots;
- confidence;
- deterministic initial case card или результат явной генерации через GigaChat.

Внутренний RAG source snapshot сохраняется в `Message.sources` для audit, но текущий
admin message API его не возвращает.

Начальная карточка создаётся без LLM-вызова: `title` берётся из первого user
message, а пустые `problem` и `result` заполняются значением
`Не указано в тикете`. Все три поля обязательны и могут быть отредактированы до
Approve.

Действия:

```text
[ Approve ] → добавить кейс в БЗ
[ Reject ]  → не добавлять
```

Только после `Approve` case card публикуется и проходит обычный pipeline:

```text
Docling / нормализация
        ↓
    chunking
        ↓
    BGE-M3
        ↓
    Qdrant
```

То есть закрытие **не обучает систему автоматически** — кандидат только создаётся
для ручной проверки, а `Approve` публикует его в БЗ.

Если пользователь выбирает:

```text
Нет, AI ошибся
```

оценка сохраняется, а закрытый тикет попадает в очередь:

```text
Ошибки AI
```

где администратор анализирует причину и после разбора может удалить чат.

---

#### Этап 2B. Confidence не прошёл порог

После построения общего `GenerationContext` backend сначала вызывает structured
confidence assessment. Его контракт содержит только confidence:

```python
class ConfidenceAssessment(BaseModel):
    confidence: float = Field(ge=0, le=1)
```

Технический confidence prompt захардкожен в backend, не хранится в `SystemPrompt` и
не показывается администратору. Он оценивает вопрос, историю, RAG evidence, screenshot
analysis и runtime attachments с учётом текущего `operator_escalation_threshold`.

Decision policy работает так:

```python
confidence = assessment.confidence
if confidence >= operator_escalation_threshold:
    stream_user_answer_with_same_context()
elif clarification_is_allowed:
    persist_clarification_message()
else:
    switch_to_operator_mode()
```

При низком confidence второй GigaChat call не выполняется. Уточнение остаётся
ограниченным двумя раундами и использует существующую детерминированную policy; если
уточнение не помогает, backend в одной транзакции переводит Dialog в
`operator_support` и сохраняет system Message с confidence и внутренним snapshot
`Message.sources`.

Системное сообщение переживает reload. Пользователь продолжает тот же тикет, а
эскалированное обращение появляется в панели оператора. Source snapshot хранится
в backend для аудита, но текущий публичный `MessageDto` его не возвращает.

---

#### Этап 3. Режим оператора + ручной шаблон GigaChat

После подключения оператора GigaChat **не отправляет ответы пользователю напрямую**
и не запускается автоматически на новых сообщениях. Новое пользовательское
сообщение сохраняется и передаётся оператору событием `user_message`.

Для ручной подсказки используется отдельный редактируемый системный prompt:

```text
SystemPrompt(type=operator_gigachat)
```

Назначенный оператор сам запускает генерацию:

```text
POST /api/operator/dialogs/{dialogId}/template
→ GenerationContextService читает актуальную историю и последнее user message
→ BGE-M3 + Qdrant находят evidence
→ GigaChat возвращает OperatorTemplateDto
```

Контекст включает скользящую историю, RAG evidence и все attachments диалога; последнее
пользовательское сообщение используется как current text. Результат не сохраняется в БД: frontend
держит template state отдельно для каждого `dialogId`. `dialog_updated_at` в
ответе endpoint позволяет запретить вставку, если история изменилась во время
генерации.

В панели оператора шаблон можно вставить в composer, отредактировать, скопировать
или проигнорировать. Он никогда не отправляется автоматически. Каждое новое
сообщение пользователя требует явного нажатия «Сгенерировать шаблон».

---

#### Этап 4. Завершение операторского тикета

После решения проблемы оператор закрывает тикет:

```text
Dialog.status = closed
```

После закрытия тикет ожидает итоговую оценку пользователя, а его pending-кандидат
уже доступен администратору.

Пользователь отмечает:

```text
[ Да, помогло ]
```

Оператор не создаёт кандидата вручную: при закрытии того же Dialog backend автоматически
создаёт pending-кандидата, а оценка пользователя хранится независимо и может быть
`helpful`, `ai_error` или отсутствовать.

---

#### Три системных промпта

В приложении храним три независимо редактируемых системных промпта:

```text
SystemPrompt(type=user_support)
→ AI самостоятельно отвечает конечному пользователю

SystemPrompt(type=operator_gigachat)
→ AI GigaChat генерирует шаблон ответа для оператора

SystemPrompt(type=knowledge_card)
→ AI GigaChat заполняет поля карточки из закрытого тикета
```

Все три хранятся в PostgreSQL и редактируются через админку без перезапуска backend.

При смене режима тикета:

```text
ai_support
    ↓ confidence < threshold
operator_support
```

backend прекращает автоматическую AI-обработку новых сообщений.

Остальная инфраструктура остаётся той же:

```text
GenerationContextService
BGE-M3
Qdrant
rag_top_k
attachments
GigaChatProvider
```

                `GenerationContextService` используется для единого user confidence/answer
                turn, ручного operator template и Knowledge Card, поэтому user runtime не
                создаёт отдельный RAG pipeline или AI-агента.

---

#### Почему эта схема закрывает исходные требования

```text
Вопрос-ответ
→ AI самостоятельно ведёт пользователя до решения

Автоматическое подключение к чату
→ после эскалации тот же тикет переходит оператору; GigaChat доступен оператору
только как ручной шаблон ответа

Анализ изображений
→ attachments/screenshots доступны в любом сообщении обоих режимов

Управление БЗ / обучение
→ все закрытые тикеты попадают в KnowledgeCandidate
и публикуются только после ручной модерации администратора
```

Получается один сквозной lifecycle:

```text
USER
↓
AI SUPPORT
├── решено → closed → KnowledgeCandidate
│                         ├→ feedback helpful / ai_error / unrated
│                         └→ admin Approve / Reject
│
├── ошибся → closed → ai_error → очередь «Ошибки AI»
│
└── confidence < threshold
            ↓
        OPERATOR SUPPORT
            ↓
        MANUAL AI TEMPLATE
            ↓
            closed
            ↓
        KnowledgeCandidate уже создан при close
            ↓
        feedback helpful / ai_error / unrated
            ↓
        admin Approve / Reject
```

### Confidence диалога и эскалация

Для каждого диалога храним:

```text
dialog_confidence ∈ [0, 1]
```

При создании нового диалога:

```text
dialog_confidence = 1.0
```

                Во время каждого AI user turn значение обновляется результатом первого
                confidence call. Это предварительная оценка достаточности текущего
                контекста до формирования ответа.

#### GigaChat-вызовы на пользовательский turn

```text
USER MESSAGE
    ↓
[screenshot? → CALL #0 structured parse]
    ↓
RAG retrieval
    ↓
                ContextBuilder.build() — один GenerationContext
                    ↓
                GenerationGate.acquire()
                    ↓
                CALL #1: structured ConfidenceAssessment
                hardcoded confidence prompt + threshold
                    ↓
                confidence SSE event
                ┌──────────────────────────────┼─────────────────────┐
                │                              │
                confidence >= threshold        confidence < threshold
                │                              │
                ↓                              ↓
                CALL #2: user answer stream     no CALL #2
                → assistant_token SSE           clarification/operator
                → assistant_done
                ```

                Оба call используют один и тот же базовый контекст: recent history, текущий
                вопрос, RAG evidence, screenshot analysis, runtime attachments и snapshot
                runtime settings. Между ними нет повторного retrieval или перестроения истории.
                Первый call не генерирует пользовательский ответ. При достаточной уверенности
                второй call использует только `SystemPrompt(type=user_support)` и отправляет
                очищенные chunks через SSE сразу по мере получения.

                Контракт confidence:

                ```python
                class ConfidenceAssessment(BaseModel):
                    confidence: float = Field(ge=0, le=1)
                ```

                Confidence получает полный общий контекст, но не получает редактируемый
                `SystemPrompt(type=user_support)`: используется только hardcoded technical
                instruction. Если confidence ниже порога, второй call не выполняется.
                Уточнение разрешено максимум два раза по существующей policy; затем Dialog
                переводится в `operator_support`.

#### Поведение после подключения оператора

                В `operator_support` новые пользовательские сообщения не запускают confidence/answer или
автоматический ответ. Они сохраняются в историю и передаются оператору через SSE.
Шаблон генерируется только явным
`POST /api/operator/dialogs/{dialogId}/template`.

#### Порог эскалации

Единственная изменяемая в админке настройка:

```text
operator_escalation_threshold ∈ [0, 1]
default = 0.80
```

                Она передаётся в общий `GenerationContext` и используется backend decision policy
                после первого confidence call.
Остальные runtime AI/RAG settings также редактируются в этой форме и сохраняются
одной atomic mutation; backend валидирует их перед commit.

Явная просьба пользователя о специалисте определяется детерминированно по набору
операторских маркеров. В этом случае LLM pipeline обходится: backend сохраняет
confidence `0`, system Message и сразу переводит Dialog в `operator_support`.

#### Глобальный admission и один доступный поток

Для физлица доступен один generation-поток. Внутри одного процесса provider и сервисы
используют re-entrant `GenerationGate`. Дополнительно `TurnCoordinator` не допускает
два AI user turn в одном процессе, а PostgreSQL:

```text
pg_advisory_xact_lock(712031043)
+ persisted Message.processing_status IN (pending, processing)
```

глобально, между backend workers, не допускает новый user AI turn до завершения
предыдущего. Эта admission-блокировка относится к пользовательским AI-turn, а не ко
всем generation/file/vision вызовам; локальный `GenerationGate` между replicas не
заменяет распределённую очередь.

                Обычный успешный turn требует двух последовательных generation-вызовов:
                confidence, затем streaming user answer. Screenshot добавляет отдельный
                structured parse до retrieval. Structured output также используется для явной
                генерации Knowledge Card; KnowledgeCandidate модерации создаётся без этого
                пользовательского pipeline.

### Финальная оценка завершённого тикета

Оценивать качество решения можно **только после завершения текущего чата / тикета**.

Пока диалог активен, кнопки оценки не показываем.

После перехода:

```text
Dialog.status = closed
```

пользователю показываем финальную оценку:

```text
Решение помогло?

[ Да, помогло ]    [ Нет, AI ошибся ]
```

Оценка относится ко **всему завершённому тикету**, а не к отдельному сообщению.

Это важно, чтобы в административные очереди попадали только законченные кейсы с полным контекстом разговора.

#### Вариант 1. Решение AI помогло

Если пользователь выбирает:

```text
Да, помогло
```

backend создаёт финальную оценку:

```text
DialogFeedback
- dialog_id
- verdict = helpful
- created_at
```

Если тикет был решён AI без участия оператора, candidate уже создаётся в транзакции
закрытия:

```text
KnowledgeCandidate(status = pending)
```

В очередь ручной проверки БЗ логически относятся:

- исходный вопрос;
- полный завершённый диалог;
- финальный ответ AI;
- внутренний snapshot использованных RAG sources;
- confidence последнего ответа;
- пользовательскую оценку `helpful`;
- deterministic initial или явно сгенерированную case card.

В текущем API source snapshot не входит в `MessageDto` и не отображается в frontend.

Администратор после проверки:

```text
Approve → добавить в БЗ
Reject  → не добавлять
```

#### Вариант 2. AI ошибся

Если пользователь выбирает:

```text
Нет, AI ошибся
```

создаём:

```text
DialogFeedback
- dialog_id
- verdict = ai_error
- created_at
```

и помещаем завершённый тикет в отдельную административную очередь:

```text
Ошибки AI
```

В карточке ошибки администратор видит через текущий API:

- полный завершённый диалог;
- вопрос пользователя;
- ответы AI;
- confidence по ответам;
- source snapshot только во внутреннем backend storage, не в `MessageDto`;
- snapshot System Prompt и GigaChat-модели из `MetricEvent`, если metric существует;
- snapshot порога эскалации для escalated user turn;
- пользовательскую отметку `AI ошибся`.

Эта очередь нужна не для автоматического обучения модели, а для **ручного анализа качества системы**:

- проблема retrieval;
- плохой/неактуальный документ БЗ;
- недостаточный System Prompt;
- неверная оценка confidence;
- ошибка понимания изображения;
- другая причина.

После анализа администратор может:

- исправить БЗ, System Prompt или runtime AI/RAG settings;
- **удалить разобранный ошибочный чат**, чтобы не засорять рабочую БД.

В карточке ошибочного тикета доступны действия:

```text
[ Открыть чат ]
[ Удалить чат ]
```

Удаление разрешено только для уже завершённого ошибочного тикета:

```text
Dialog.status = closed
AND
DialogFeedback.verdict = ai_error
```

Перед hard delete `DialogService` проверяет связанный `KnowledgeCandidate`:

```python
candidate = KnowledgeCandidate.get(dialog_id=dialog_id)

if candidate and candidate.status == "pending":
    raise Conflict("Сначала отклоните кандидата в БЗ")

if candidate and candidate.status == "approved":
    raise Conflict(
        "Диалог связан с опубликованным документом БЗ; "
        "сначала удалите/отвяжите опубликованный материал"
    )
```

Статический FK не может выразить условный RESTRICT по статусу candidate, поэтому эта проверка находится в application service.

Если candidate отсутствует или уже `rejected`, выполняется hard delete.

DB-level cascade:

```text
Dialog
├── Message                    ON DELETE CASCADE
│   └── Attachment             ON DELETE CASCADE
├── DialogFeedback             ON DELETE CASCADE
└── KnowledgeCandidate         ON DELETE CASCADE
```

Связанные локальные файлы/screenshots удаляются из storage, а существующие `gigachat_file_id` удаляются из GigaChat Files API.

Перед удалением показываем подтверждение:

```text
Удалить этот чат без возможности восстановления?

[ Отмена ] [ Удалить ]
```

Для MVP используем **hard delete** без корзины и восстановления.

Агрегированные `MetricEvent` можно не удалять, чтобы очистка старого текста диалога не ломала уже собранную статистику.

#### Ограничение оценки

Для одного завершённого тикета пользователь оставляет одну итоговую оценку:

```text
helpful
или
ai_error
```

До `Dialog.status = closed` оценка недоступна.

Таким образом:

```text
ACTIVE CHAT
    ↓
решение / эскалация / продолжение общения
    ↓
CLOSED TICKET
    ↓
    pending KnowledgeCandidate уже создан при close
    ├── helpful  → сохраняется оценка + candidate
    ├── ai_error → сохраняется оценка + очередь «Ошибки AI»
    └── unrated  → ожидает оценку
```

### Runtime sequence

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant API as FastAPI
    participant EMB as BGE-M3
    participant Q as Qdrant
    participant G as GigaChat
    participant E as Operator

    U->>API: message + optional attachment

    par Prompt branch
        API->>EMB: embed(user prompt + recent history)
        EMB-->>API: prompt dense/sparse query
    and Screenshot branch
        API->>G: CALL #0 screenshot parse
        G-->>API: extracted text + visual summary
        API->>EMB: embed(parsed screenshot)
        EMB-->>API: screenshot dense/sparse query
    end
    API->>Q: hybrid retrieval + dense preflight + rank fusion
    Q-->>API: merged rag_top_k evidence or no_match

    API->>G: Call #1 structured confidence
    G-->>API: {confidence}
    API-->>U: SSE confidence event

    alt confidence >= threshold
        API->>G: Call #2 user answer with same context
        G-->>API: answer chunks
        API-->>U: SSE assistant_token...
        API-->>U: SSE assistant_done
    else confidence < threshold
        alt clarification is useful and policy allows it
            API-->>U: SSE assistant_done with clarification question
        else escalation required
            API->>E: switch same Dialog to operator_support
            API-->>U: SSE operator_connected
        end
    end
```

## 12. RAG: ingestion, retrieval и управление контекстом

```text
Постоянная БЗ:
документ → Docling → chunking → BGE-M3 → Qdrant

Runtime:
вопрос + свежая история → BGE-M3 ─┐
скриншот → GigaChat parse → BGE-M3 ─┴→ Qdrant hybrid → dense preflight → RRF → rag_top_k
                                                                        ↓
                                                     confidence → threshold → answer/decision
```

### Два разных сценария работы с файлами

Ключевое правило:

> **Не размер файла определяет, нужен ли Docling. Определяет назначение файла.**

Есть два независимых пути.

#### A. Постоянный источник базы знаний → всегда ingestion в RAG

Любой документ, который администратор добавляет в централизованную БЗ — PDF, DOCX, HTML, Markdown — должен быть распарсен, разбит на chunks, векторизован локально и сохранён в Qdrant.

```text
KB document
    ↓
Docling
    ↓
structure-aware chunks
    ↓
BGE-M3 dense + sparse
    ↓
Qdrant
```

Это относится и к маленькому PDF на 3 страницы, и к руководству на 3000 страниц.

Почему: иначе документ нельзя нормально искать вместе с остальной БЗ, фильтровать по metadata, переиспользовать между запросами и оценивать Recall@k. Источник сохраняется для backend evidence/audit; текущий public UI его не отображает.

#### B. Разовое вложение в пользовательском чате → можно напрямую в GigaChat

Если пользователь прикладывает файл **только к текущему вопросу**, его не обязательно индексировать.

```text
chat attachment
    ↓
GigaChat Files API
    ↓
file_id
    ↓
same chat/completions request
```

GigaChat нативно поддерживает документы и изображения через Files API + `attachments`.

Для runtime-файла backend обязательно:

1. загружает его через `POST /files` с `purpose="general"`;
2. сохраняет полученный `gigachat_file_id`;
3. передаёт `file_id` в `messages[].attachments`;
4. после завершения жизненного цикла удаляет remote-файл через `/files/{file}/delete`.

Примеры:

- screenshot ошибки;
- небольшой PDF «посмотри этот отчёт»;
- DOCX/Excel, который относится только к текущему обращению.

Лимиты GigaChat: изображение до 15 MB, текстовый документ до 40 MB. При этом допустимый по размеру текстовый файл всё равно может не поместиться в context window и привести к HTTP 422.

Если пользователь/администратор позже нажмёт **«Добавить в базу знаний»**, оригинал из нашего storage проходит обычный ingestion через Docling → BGE-M3 → Qdrant.

#### Почему не отправляем всю БЗ файлами напрямую в GigaChat

Files API — это механизм контекста конкретного generation-запроса, а не замена поисковому индексу.

При большом количестве документов возникнут:

- рост входного контекста;
- лишний расход generation-токенов;
- невозможность эффективно искать по сотням документов;
- более слабая управляемость источников и metadata;
- ограничение контекстного окна модели.

Поэтому **native files = runtime attachments**, а **Docling+BGE-M3+Qdrant = persistent knowledge base**.

### Preprocessing / ingestion базы знаний

#### Этап 1. Приём и регистрация документа

Администратор загружает файл в выбранный раздел БЗ.

Backend:

1. проверяет MIME/расширение;
2. считает `sha256` для защиты от случайных дублей;
3. сохраняет оригинал;
4. создаёт `KnowledgeDocument`;
5. ставит статус `processing`;
6. запускает ingestion pipeline.

Поддерживаемые форматы обязательного MVP:

- PDF;
- DOCX;
- HTML;
- Markdown.

Для старых `.doc` можно добавить конвертацию позднее; не делаем её блокером MVP.

#### Этап 2. Структурный парсинг через Docling

Для **всех документов, которые становятся частью постоянной БЗ**, основной parser — **Docling**, независимо от размера файла.

Причина: он приводит PDF/DOCX/HTML/Markdown к единому структурированному представлению и умеет сохранять:

- заголовки и иерархию разделов;
- списки и пошаговые инструкции;
- таблицы;
- подписи;
- страницы/позиции;
- metadata документа.

Для RAG это лучше, чем «PDF → сплошной plain text», потому что инструкции 1С часто зависят от структуры: раздел → форма → поле → последовательность действий.

```text
PDF / DOCX / HTML / MD
        ↓
    Docling
        ↓
structured document
```

#### Этап 3. Нормализация

Перед chunking:

- убираем повторяющиеся headers/footers и мусор;
- нормализуем пробелы и переносы;
- **не удаляем** технические символы, коды ошибок, названия объектов 1С и номера версий;
- сохраняем заголовочную цепочку (`heading_path`);
- таблицы сериализуем так, чтобы названия колонок оставались рядом со строками;
- добавляем источник и business metadata.

Пример metadata:

```json
{
  "section_id": "1c_docs",
  "source_type": "official_1c_docs",
  "title": "Руководство пользователя",
  "heading_path": ["Бухгалтерия", "Закрытие месяца", "Регламентные операции"],
  "page": 143,
  "one_c_version": "3.0",
  "tags": [],
  "chunk_index": 0,
  "answer_eligible": true
}
```

В текущей модели нет отдельного `resolution_status`. Поле `answer_eligible`
записывается в payload новых векторов как технический флаг, но retrieval сейчас не
фильтрует по нему; доступность evidence определяется enabled section/document и
`index_status = indexed`.

#### Этап 4. Специальная обработка журналов обращений

Журнал обращений не надо индексировать как сырой длинный чат.

Для кейса, который администратор хочет опубликовать, итоговая Markdown-карточка
имеет логическую структуру:

```text
Проблема:
...

Симптомы / текст ошибки:
...

Контекст:
конфигурация / версия / форма

Решение:
1. ...
2. ...
3. ...

Результат:
успешно
```

Текущий обычный close-flow не делает LLM-суммаризацию: он создаёт deterministic
candidate с обязательными полями `title`, `problem`, `result`, где отсутствующие
данные представлены как `Не указано в тикете`. LLM-заполнение доступно отдельной
admin-кнопкой. LLM-суммаризацию тикетов как offline enrichment можно добавить
позднее.

##### Закрытые кейсы: автоматический candidate → модерация администратором

Любой закрытый Dialog, решённый AI или оператором, **не добавляется в БЗ автоматически**.
В момент закрытия создаётся один pending `KnowledgeCandidate`; пользовательская
оценка сохраняется отдельно и не является условием создания candidate.

Lifecycle кандидата:

```text
AI или оператор решил обращение
        ↓
Dialog закрыт
        ↓
создаётся initial карточка-кандидат
        ↓
очередь модерации администратора
        ↓
┌──────────────┐
│              │
APPROVE        REJECT
│              │
↓              ↓
индексация      остаётся только
в основную БЗ   в истории/аналитике
```

Администратор перед публикацией видит:

- исходный вопрос пользователя;
- контекст диалога;
- финальное решение AI или оператора;
- итоговую оценку пользователя, если она есть;
- deterministic initial карточку или результат явной генерации через GigaChat;
- при необходимости — возможность отредактировать карточку перед `Approve`.

Source snapshot сохраняется внутри backend для audit, но текущий candidate/detail
API его не возвращает.

Статусы кандидата:

```text
pending
approved
rejected
```

Только после `approved` case card становится permanent KB document.

Approve всегда использует `DEFAULT_CASE_SECTION_ID`; selector в UI отсутствует:

```text
DEFAULT_CASE_SECTION_ID
→ системный раздел «Журнал обращений»
```

Этот раздел создаётся при старте приложения из SQLAlchemy-моделей и seed-данных и
защищён backend от удаления через admin API.

Approve выполняется как retryable workflow с компенсацией внешних операций:

```python
def approve(candidate, generated_card=None):
    if candidate.status == "approved":
        return candidate
    if generated_card is not None:
        candidate.generated_card = generated_card
    doc = get_or_create_document(
        storage_key=f"case-cards/{candidate.id}.md",
        section_id=DEFAULT_CASE_SECTION_ID,
        source_type="resolved_case",
    )
    if doc.index_status != "indexed":
        ingest_permanent_document(doc)
    # тот же pipeline:
    # Markdown → Docling → chunking → BGE-M3 → Qdrant

    candidate.status = "approved"
    candidate.resulting_document_id = doc.id
```

Case card **не обходит Docling**: после materialization в Markdown она проходит тот же
permanent ingestion, что и любой другой документ БЗ. Начальная карточка создаётся
детерминированно: `title` берётся из первого user message, а отсутствующие `problem`
и `result` получают `Не указано в тикете`; администратор может отредактировать её
перед approve.

Если предыдущая попытка упала после создания документа, повторный Approve находит
тот же `case-cards/{candidate_id}.md`, переиспользует его и запускает ingestion только
если документ ещё не `indexed`. Если документ создан текущей попыткой и внешняя
операция не удалась, backend удаляет созданные storage/vector данные, насколько это
возможно, а существующий partial документ оставляет для повторной попытки.

Так система действительно пополняет БЗ закрытыми кейсами, но между закрытием тикета
и попаданием в эталонную БЗ остаётся **human-in-the-loop контроль качества**.

Тикеты с `ai_error` остаются в журнале для анализа, но отдельного флага
`resolution_status` для них нет. До ручного Approve закрытый кейс не является
permanent KB document и потому не участвует в RAG.

Для `KnowledgeDocument.source_type` в MVP:

```text
official_1c_docs
internal_kb
resolved_case
```

`resolved_case` используется только для case card, прошедших admin Approve.

### Structure-aware chunking

Не режем текст каждые N символов.

Используем **Docling `HybridChunker`**, настроенный на tokenizer BGE-M3. Docling сначала учитывает структуру документа, а затем подгоняет chunks под token budget.

Стартовые параметры для MVP:

```text
target chunk: примерно 400–700 tokens
hard max:     примерно 800 tokens
overlap:      небольшой / только там, где нужен контекст
merge peers:  true
```

Параметры являются стартовыми и должны проверяться на нашей документации 1С.

Правила:

- короткий раздел стараемся сохранить целиком;
- шаги одной инструкции не разрываем без необходимости;
- заголовок/путь раздела добавляется к chunk перед embedding;
- таблица сохраняет header;
- если процедура разрезана, chunks связываются `document_id + chunk_index`;
- каждый chunk хранит ссылку на исходный документ/страницу.

Индексируем не только:

```text
chunk.text
```

а контекстуализированную форму:

```text
Документ: Бухгалтерия предприятия
Раздел: Закрытие месяца > Регламентные операции
Версия: 3.0

<текст чанка>
```

Это помогает embedding-модели различать одинаковые термины в разных конфигурациях/разделах.

### Embeddings

Единственная модель MVP:

```text
BAAI/bge-m3
```

Основной dense vector:

```text
dimension = 1024
```

Для каждого chunk сохраняем:

- dense representation;
- sparse/lexical representation (если используем hybrid mode BGE-M3);
- metadata payload.

Индекс:

```text
Qdrant
└── knowledge_chunks
    ├── dense vector
    ├── sparse vector
    └── payload
```

### Runtime retrieval и управление контекстом моделей

#### Шаг 1. GigaChat: размер скользящего окна

В админ-панели хранится один нормализованный параметр:

```text
gigachat_context_ratio ∈ [0, 1]
```

Он задаёт **размер скользящего окна GigaChat** как долю от полного контекстного окна активной модели. Это верхняя граница общего context budget одного запроса.

Например, если:

```text
model_context_limit = 128000
gigachat_context_ratio = 0.10
```

то общий budget приложения на один запрос:

```text
gigachat_total_budget =
    floor(model_context_limit * gigachat_context_ratio)

= 128000 * 0.10
= 12800 tokens
```

В этот budget должны уложиться:

```text
GigaChat request budget
│
├── system prompt
├── текущий запрос пользователя
├── RAG evidence
├── предыдущие сообщения диалога
├── attachments / их контекст
└── генерируемый ответ
```

##### Максимальный размер ответа GigaChat

> **Не путать:** `gigachat_context_ratio` — это размер скользящего окна/общего context budget запроса, а `gigachat_max_output_tokens` — только максимальная длина нового ответа GigaChat.

Параметр `max_tokens` передаётся непосредственно в запрос `chat/completions` и задаёт **максимальное количество токенов, которое модель может потратить на генерацию ответа**.

Параметр редактируется в админ-панели и передаётся provider-у:

```text
gigachat_max_output_tokens
```

В API:

```text
max_tokens = gigachat_max_output_tokens
```

По документации GigaChat значение должно быть `> 0`; значение по умолчанию — **2048 токенов**.

Пример настроек:

```text
gigachat_context_ratio      = 0.10
gigachat_max_output_tokens  = 2048
```

Если выбранная модель имеет:

```text
model_context_limit = 128000
```

то:

```text
gigachat_total_budget =
    floor(128000 * 0.10)
    = 12800 tokens

gigachat_input_budget =
    12800 - 2048
    = 10752 tokens
```

То есть `gigachat_max_output_tokens` напрямую определяет, сколько места мы заранее оставляем модели под ответ.

Формула:

```text
gigachat_input_budget =
    floor(model_context_limit * gigachat_context_ratio)
    - gigachat_max_output_tokens
```

Backend валидирует настройку:

```text
0 < gigachat_max_output_tokens < gigachat_total_budget
```

Эти значения редактируются через admin API в текущем MVP; backend проверяет, что
выбранная модель существует, ratios находятся в диапазоне `[0, 1]`, а
`gigachat_max_output_tokens` положителен и меньше общего budget. При уменьшении
`gigachat_max_output_tokens` больше budget остаётся под историю/RAG, а при увеличении
модель может дать более длинный ответ.

##### Что обрезается при нехватке места

Главный эластичный компонент — **предыдущие сообщения диалога**.

Приоритет сборки payload:

```text
1. system prompt                    обязательный
2. текущий запрос пользователя      обязательный
3. актуальный RAG evidence          приоритетный
4. attachments                      при наличии
5. предыдущие сообщения диалога     заполняют остаток и обрезаются первыми
```

Backend:

1. вычисляет `gigachat_input_budget`;
2. учитывает обязательные части;
3. считает оставшийся budget;
4. идёт по истории от новых сообщений к старым;
5. добавляет сообщения, пока они помещаются;
6. более старая история остаётся в PostgreSQL, но не отправляется в текущий запрос.

Если даже без истории payload слишком велик:

1. `history = 0`;
2. уменьшаем количество RAG chunks;
3. если проблема в слишком большом runtime-файле — не пытаемся отправить его целиком обычным attachment.

`gigachat_context_ratio = 1.0` означает, что приложение может использовать почти всё контекстное окно модели, но backend всё равно вычитает `gigachat_max_output_tokens` под ответ.

Для MVP разумное стартовое значение:

```text
gigachat_context_ratio = 0.10
```

Для моделей с окном 128k это даёт около 12.8k общего budget на один запрос — более чем достаточно для обычного диалога техподдержки и нескольких RAG chunks.

#### Шаг 1.1. BGE-M3: коэффициент embedding-контекста

Для embedding-модели используется второй нормализованный параметр:

```text
embedding_context_ratio ∈ [0, 1]
```

У `BAAI/bge-m3` максимальная длина входной последовательности:

```text
embedding_model_context_limit = 8192 tokens
```

Поэтому:

```text
embedding_input_budget =
    floor(8192 * embedding_context_ratio)
```

Например:

```text
embedding_context_ratio = 0.25

8192 * 0.25 = 2048 tokens
```

В отличие от GigaChat, **никакой output reserve для embedding-модели не нужен**: BGE-M3 не генерирует текстовый ответ, а только превращает вход в векторное представление.

Embedding-контекст собирается так:

```text
embedding_input_budget
│
├── текущий запрос пользователя      обязательный
└── предыдущие сообщения диалога     заполняют остаток
                                    и обрезаются первыми
```

То есть:

```text
current message
+ максимально свежий хвост истории
        ↓
    BGE-M3
        ↓
dense + sparse representation
        ↓
    Qdrant
```

Если заданное значение слишком мало даже для текущего пользовательского сообщения,
backend всегда сохраняет текущий запрос целиком и не добавляет историю.

Для MVP разумное стартовое значение:

```text
embedding_context_ratio = 0.25
```

то есть примерно 2048 токенов поискового контекста.

#### Как выглядят настройки администратора

В UI доступны следующие controls:

```text
Размер скользящего окна GigaChat
[────●────────────] 10%

Максимальный размер ответа
[ numeric input ] 2048 tokens

Контекст Embeddings
[──────●──────────] 25%
```

В backend они хранятся как числа:

```text
gigachat_context_ratio     = 0.10
gigachat_max_output_tokens = 2048
embedding_context_ratio    = 0.25
```

Preview budget пересчитывается сразу при изменении модели или ratios; перед сохранением
frontend проверяет значения, а backend повторяет всю валидацию.

Например:

```text
ratio = 0.10

контекст модели 128000 → budget 12800
контекст модели  64000 → budget  6400
```

Таким образом администратору не нужно вручную пересчитывать токены; model options
возвращаются backend для Select и typed capabilities/preview.

#### Шаг 2. Hybrid retrieval

Внутри одного Qdrant-запроса запускаются два prefetch-поиска:

```text
A. Dense search
BGE-M3 → semantic similarity

B. Sparse / lexical search
точные термины, коды ошибок, названия полей
```

Перед hybrid fusion backend выполняет dense preflight с
`score_threshold = 0.35`. Если у чанка нет достаточно близкого dense-сигнала, он
не может попасть в результат только за счёт sparse-поиска. После этого Qdrant
объединяет dense и sparse списки через **RRF (Reciprocal Rank Fusion)**.

Почему hybrid особенно полезен для 1С:

```text
"не проводится документ после закрытия месяца"
        → semantic/dense сигнал

"Ошибка 10.2.17", "РегистрНакопления.X", точное имя поля
        → lexical/sparse сигнал
```

Одним dense-поиском легко потерять точный код; одним lexical — перефразированный вопрос.

#### Шаг 3. Управление доступностью разделов и документов

Сложные runtime-фильтры по конфигурации, версии 1С, типу источника и другим metadata **не используем в MVP**.

Оставляем два простых механизма управления БЗ:

```text
KnowledgeSection.is_enabled
KnowledgeDocument.is_enabled
```

Администратор может:

- выключить отдельный документ;
- выключить целый раздел БЗ.

Если раздел выключен:

```text
KnowledgeSection.is_enabled = false
```

то **все документы внутри него временно исключаются из RAG**, независимо от собственного флага документа.

Документ участвует в retrieval только если:

```text
section.is_enabled == true
AND
document.is_enabled == true
```

При выключении раздела индивидуальные значения `KnowledgeDocument.is_enabled` не меняем.

Например:

```text
раздел = OFF
документ A = ON
документ B = OFF
```

Пока раздел выключен:

```text
A → не участвует в RAG
B → не участвует в RAG
```

Если раздел снова включить:

```text
A → снова участвует
B → остаётся выключенным
```

То есть флаг раздела — это **master switch** для всех документов внутри него.

Физически документы и chunks не удаляются и повторная индексация не требуется.

#### Шаг 4. Отбор evidence и `rag_top_k`

После hybrid search dense и sparse результаты объединяются через RRF. Если в
запросе есть и prompt-, и screenshot-query, `RAGService` дополнительно выполняет
equal-weight rank fusion по `weight / (60 + rank)`, дедуплицирует vector IDs и
при необходимости увеличивает candidate limit до трёх раз, чтобы отфильтрованные
SQL-строки не оставили меньше `top_k` evidence.

Администратор задаёт отдельный параметр в UI:

```text
rag_top_k
```

Он определяет, сколько лучших chunks после объединения рейтингов будет передано в GigaChat как RAG evidence.

Например:

```text
rag_top_k = 6
```

Runtime:

```text
dense preflight (threshold 0.35) ─┐
dense + sparse prefetch → Qdrant RRF ─┼→ equal-weight rank fusion → top 6 → GigaChat
screenshot/prompt queries ──────────┘
```

Стартовое значение MVP:

```text
rag_top_k = 6
```

В UI `rag_top_k` редактируется; backend policy задаёт нижнюю границу:

```text
rag_top_k >= 1
```

Отдельного пользовательского верхнего ограничения в UI нет.

Чем больше `rag_top_k`:

- больше потенциально полезного контекста;
- больше токенов занимает RAG;
- выше риск передать модели шум и дубли.

Чем меньше:

- меньше расход контекста;
- выше риск не передать нужный фрагмент.

На MVP никаких сложных reranker/dedup pipeline не добавляем. Дедупликация делается
по `vector_id` во время rank fusion; соседние chunks отдельно не объединяются.

## 13. GigaChat + LangChain/GigaChain

Этот раздел фиксирует детали интеграции, подтверждённые актуальной официальной документацией GigaChat API и реализованные через `langchain-gigachat`. Контракт backend с GigaChat определён через LangChain primitives и provider boundary.

### Роль GigaChat в продукте

GigaChat — **основная интеллектуальная модель пользовательского сценария**.

В runtime GigaChat получает:

- системный prompt выбранного режима: `SystemPrompt(type=user_support)` для AI-ответа или `SystemPrompt(type=operator_gigachat)` для ручного шаблона;
- для ручного заполнения карточки по кнопке или явного legacy/admin backfill — `SystemPrompt(type=knowledge_card)` и structured output;
- текущий вопрос пользователя или последнее user message тикета для шаблона;
- хвост истории диалога, собранный `ContextBuilder`;
- найденные RAG evidence chunks;
- текущий `operator_escalation_threshold`;
- runtime attachments: screenshot / документ, если приложены.

В user `ai_support` pipeline backend один раз собирает `GenerationContext`, затем
выполняет hardcoded structured confidence call. Если confidence проходит порог,
второй последовательный call с `SystemPrompt(type=user_support)` формирует ответ и
стримится пользователю. При низком confidence второй call не запускается: применяется
существующая clarification/escalation policy. В operator pipeline отдельный
generation-вызов формирует шаблон ответа; он не отправляется пользователю автоматически.

Анализ screenshot выполняется отдельным structured vision-вызовом до retrieval.

`confidence` оценивается первым отдельным structured-вызовом в `ai_support` до
формирования ответа и до его публикации пользователю. Этот вызов использует только
hardcoded технический confidence prompt и текущий порог; редактируемый
`SystemPrompt(type=user_support)` в него не передаётся. Structured-вызовы также
используются для screenshot parse и явного заполнения Knowledge Card.

Локальные BGE-M3 embeddings не являются вызовом GigaChat API и работают независимо.

### Авторизация и жизненный цикл Access Token

Для текущего MVP используется scope:

```text
GIGACHAT_API_PERS
```

Авторизационный ключ (`Authorization Key`) создаётся из `Client ID + Client Secret` и используется для получения Access Token через:

```text
POST https://ngw.devices.sberbank.ru:9443/api/v2/oauth
```

Для OAuth-запроса передаётся уникальный:

```text
RqUID = uuid4
```

Полученный Access Token:

```text
Authorization: Bearer <access_token>
```

используется для запросов к:

```text
https://api.giga.chat/
```

По официальной документации Access Token действует **30 минут**.

Архитектурное правило:

```text
Frontend
✕ не знает Authorization Key / Client Secret / Access Token

Backend / GigaChatProvider
✓ владеет credentials
✓ получает/обновляет Access Token
✓ выполняет все запросы GigaChat
```

Если SDK / `langchain-gigachat` самостоятельно управляет обновлением Access Token, не дублируем эту логику вручную — `GigaChatProvider` только инкапсулирует клиент.

Секреты хранятся только в environment/secrets:

```text
GIGACHAT_CREDENTIALS
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_CA_BUNDLE_FILE
```

Authorization Key и Client Secret не сохраняются в PostgreSQL и не возвращаются через API frontend.

Документация:

- https://developers.sber.ru/docs/ru/gigachat/quickstart/ind-using-api

### TLS и сертификаты Минцифры

Для соединения с GigaChat API нужен корневой сертификат НУЦ Минцифры. Без него возможна ошибка:

```text
SSL: CERTIFICATE_VERIFY_FAILED
```

Для MVP на Linux/Docker используем один из корректных вариантов:

```text
A. установить Russian Trusted Root/Sub CA
в системное CA-хранилище контейнера/ОС

или

B. передать путь к PEM/CRT через ca_bundle_file
```

Предпочтительный вариант для нашего Docker deployment:

```text
Docker image
↓
установлены доверенные сертификаты Минцифры
↓
GigaChat client
↓
SSL verification = ON
```

`verify_ssl_certs=False` **не является штатным production/MVP-решением**. Он встречается в примерах SDK, но в нашем развёртывании валидацию TLS не отключаем.

Для `gigachat` / `langchain-gigachat` документация поддерживает:

```python
ca_bundle_file="/path/to/russian_trusted_root_ca_pem.crt"
```

Документация:

- https://developers.sber.ru/docs/ru/gigachat/certificates?OS=debian-ubuntu

### Квоты, один generation-поток и очередь запросов

Для физического лица GigaChat API предоставляет:

> **1 одновременный поток**, независимо от Freemium или платных токенов.

Для текущей архитектуры на один пользовательский turn допускаются **два последовательных generation-запроса**:

```text
    CALL #1 → structured ConfidenceAssessment
    CALL #2 → user answer stream
```

Они никогда не выполняются параллельно.

И дополнительно сериализуем обращения к GigaChat внутри backend:

```python
generation_gate = GenerationGate()  # re-entrant asyncio gate
```

Схематично:

```text
request A ─┐
request B ─┼→ GenerationGate → GigaChatProvider → GigaChat API
request C ─┘
```

Admission пользовательских AI-turn дополнительно защищён глобально:

```text
PostgreSQL pg_advisory_xact_lock(712031043)
+ persisted pending/processing trigger check
+ process-local TurnCoordinator
```

Поэтому новый пользовательский turn в другом чате отклоняется до завершения текущего
даже при нескольких backend workers. Локальный `GenerationGate` по-прежнему не
обеспечивает глобальную сериализацию operator-template, screenshot и Knowledge Card
generation между replicas; централизованная очередь для всех provider-вызовов остаётся
Roadmap.

Не строим длинную LLM-chain вида:

```text
classify → rewrite → vision → rerank → answer
```

Единственное осознанное разделение user generation-логики — короткий structured
confidence call, затем streaming user answer с тем же `GenerationContext`. При
достаточной уверенности answer chunks сразу публикуются через SSE; при низкой
уверенности второй call не запускается и применяется clarification/escalation policy.
Ручной operator template выполняется отдельным вызовом и не участвует в user turn.

#### Тематические ограничения

Если запрос попадает под тематические ограничения GigaChat, API может вернуть:

```text
choices.finish_reason = "blacklist"
```

Это обрабатываем как штатный результат провайдера, а не как технический exception.

Backend завершает текущий user turn как failed, не запускает следующий user-answer call
и не пытается повторять тот же запрос в бесконечном retry.

Документация:

- https://developers.sber.ru/docs/ru/gigachat/limitations

### Выбор модели

Модель **всегда указываем явно** в запросе через `model`.

Это важно, потому что SDK по умолчанию может направлять запрос в базовую модель, а
backend явно передаёт выбранную администратором модель.

Актуальное соответствие UI → API identifier:

```text
Lite  → GigaChat-2
Pro   → GigaChat-2-Pro
Max   → GigaChat-2-Max
Ultra → GigaChat-3-Ultra
```

`GigaChat-2` ориентирована на максимальную скорость и более простые задачи; `Pro` лучше следует сложным инструкциям; `Max` предназначена для более сложных задач высокого качества; `GigaChat-3-Ultra` доступна физлицам в Freemium.

В PostgreSQL:

```text
active_gigachat_model = "GigaChat-2-Pro"
```

`available_models` возвращается в typed settings response и используется frontend
для выбора модели.

`GigaChatProvider` получает model capabilities из отдельной конфигурации:

```text
ModelCapabilities
- api_model_id
- context_limit
- supports_images
- supports_structured_output
```

Так context budget автоматически пересчитывается при смене модели.

Документация:

- https://developers.sber.ru/docs/ru/gigachat/guides/selecting-a-model?lang=sh

### История чата: GigaChat не хранит её за нас

При работе через API историю нужно **явно передавать в `messages` каждого запроса**.

То есть:

```text
PostgreSQL
↓
ContextBuilder
↓
последние сообщения в пределах sliding window
↓
messages[]
↓
GigaChat
```

GigaChat не является серверным persistent-memory store нашего диалога.

Историю храним полностью в PostgreSQL, а перед каждым запросом backend формирует только актуальное окно согласно настройкам из раздела 5.5.

Текст сообщений передаём в UTF-8.

### `X-Session-ID`: кэш, а не память

GigaChat поддерживает необязательный заголовок:

```text
X-Session-ID
```

Он позволяет закэшировать повторяющуюся часть контекста.

Для каждого `Dialog` задаём стабильный session id, например:

```text
X-Session-ID = <dialog_uuid>
```

Если следующий запрос имеет тот же `X-Session-ID` и частично совпадающий контекст, GigaChat может не пересчитывать совпадающую часть.

В `usage` можно получить:

```text
precached_prompt_tokens
```

Это полезно для:

- снижения latency;
- снижения расхода тарифицируемых повторяющихся prompt-токенов;
- длинных разговорных сценариев.

Критически важно:

```text
X-Session-ID ≠ память диалога
X-Session-ID ≠ увеличение context window
```

Историю всё равно нужно передавать явно в `messages`.

По документации работа с дополнительными заголовками поддерживается Python-библиотеками GigaChat, что подходит нашему FastAPI backend.

В один `MetricEvent(event_type="user_turn")` агрегируем usage обоих user calls:

```text
prompt_tokens
completion_tokens
precached_prompt_tokens
```

Это суммы confidence и answer calls; если answer не выполнялся, сохраняется только
usage confidence call. Поля нужны для диагностики расхода контекста и не обязаны
выводиться в основной UI мониторинга.

Документация:

- https://developers.sber.ru/docs/ru/gigachat/guides/keeping-context

### Токены и context budget

GigaChat тратит токены и на prompt, и на ответ:

```text
total_tokens =
    prompt_tokens
    + completion_tokens
```

Для текстового prompt количество токенов можно оценивать через:

```text
POST /tokens/count
```

При этом разные модели могут считать токены по-разному.

В runtime сохраняем ранее выбранную схему:

```text
gigachat_total_budget =
    model_context_limit * gigachat_context_ratio

gigachat_input_budget =
    gigachat_total_budget
    - gigachat_max_output_tokens
```

Главный компонент, который сокращается при нехватке input budget:

```text
previous dialog messages
```

`POST /tokens/count` не обязан вызываться на каждом пользовательском turn: это лишний сетевой вызов. Для MVP `ContextBuilder` использует консервативную локальную оценку, а `/tokens/count` можно применять в тестах/диагностике и при настройке budget.

Фактический расход после generation сохраняется из `usage`.

Документация:

- https://developers.sber.ru/docs/ru/gigachat/quickstart/ind-using-api

### Streaming ответа

GigaChat поддерживает потоковую генерацию:

```json
"stream": true
```

Ответ приходит как:

```text
Content-Type: text/event-stream
```

по протоколу Server-Sent Events (SSE).

Финальный маркер v1-потока:

```text
data: [DONE]
```

Для user answer в текущем MVP используем цепочку:

```text
GigaChat confidence structured call
    ↓
threshold decision
    ↓
GigaChat user answer SSE
    ↓
FastAPI SSE proxy
    ↓
Frontend
```

Confidence event не содержит технический prompt. При успешном decision пользователь
видит каждый answer chunk сразу после его получения; backend сохраняет полный текст
только для завершения сообщения и аудита, а не для задержки SSE.

Важно: generation stream занимает доступный GigaChat-поток до завершения model call,
а `GenerationGate` удерживается на всём user turn: от screenshot/context preparation
до confidence, answer stream и terminal event.

Документация:

- https://developers.sber.ru/docs/ru/gigachat/guides/response-token-streaming

### Structured Output: confidence, screenshot и Knowledge Card

Structured Output используется в трёх явных местах:

1. confidence call возвращает `ConfidenceAssessment(confidence)`;
2. screenshot parse возвращает `extracted_text` и `visual_summary`;
3. admin/legacy Knowledge Card generation возвращает обязательные `title`, `problem`
   и `result`.

Через LangChain provider использует:

```python
runnable = llm.with_structured_output(
    schema,
    method="json_schema",
    include_raw=True,
)
```

Для совместимости с моделями без native JSON Schema локально допускается fallback
`json_schema → function_calling`. User answer и operator template остаются обычным
plain text. Streaming Structured Output и incremental JSON parser не нужны.

Важно: confidence call вызывается **до** user answer generation и оценивает только
достаточность общего контекста, а не готовый текст ответа.

### Runtime attachments и Files API

### Permanent KB vs runtime attachment

```text
runtime attachment
→ GigaChat Files API
→ текущий Dialog

permanent KB document
→ Docling
→ BGE-M3
→ Qdrant
```

Автоматического действия «добавить runtime-файл в БЗ» в текущем UI/API нет. Если
такой promotion появится позже, нужно использовать **оригинал из собственного
storage** и запускать обычный permanent ingestion.

Runtime attachment не становится частью постоянной БЗ автоматически.

Локальный OCR не нужен.

Разовые пользовательские файлы сначала загружаются:

```text
POST /files
purpose = "general"
```

после чего полученный:

```text
file_id
```

передаётся в generation request через `messages[].attachments`.

#### Поддерживаемые форматы, которые полезны нам

Текстовые документы:

```text
txt
doc
docx
pdf
epub
ppt
pptx
xlsx
```

Изображения:

```text
jpeg
png
tiff
bmp
```

Аудиоформаты API также поддерживаются, но они не входят в требования нашего MVP.

#### Ограничения размера

```text
text document: <= 40 MB
image:         <= 15 MB
audio:         <= 35 MB
```

Общий размер запроса с изображениями/аудио должен быть меньше 80 MB.

Ограничения GigaChat API дополнительно допускают:

```text
1 image per message
до 10 images per request
```

Политика текущего проекта строже: UI/backend разрешают до 10 runtime-вложений, но
только одно изображение на пользовательское сообщение (то есть максимум одно
изображение и до девяти текстовых файлов):

```text
до 10 runtime attachments на пользовательское сообщение
```

Ограничения GigaChat при этом соблюдаются на backend: одно изображение передаётся
в одном message-блоке, а для нескольких текстовых документов включается
`function_call="auto"`, чтобы модель обработала все документы.

#### Текстовые документы

GigaChat использует встроенную функцию `get_file_content`.

Если в одном запросе передавать несколько текстовых документов, документация требует:

```text
function_call = "auto"
```

иначе модель использует только первый документ из списка.

Backend передаёт несколько текстовых документов в одном запросе и включает автоматический режим `get_file_content`; отдельная многошаговая orchestration-цепочка для этого не нужна.

#### Большой файл и context overflow

Лимит файла в мегабайтах **не гарантирует**, что его содержимое помещается в context window модели.

Даже допустимый по размеру текстовый документ может содержать слишком много текста. В таком случае GigaChat может вернуть:

```text
HTTP 422
```

Поэтому текущий runtime flow:

```text
маленький/обычный разовый файл
→ Files API → GigaChat

слишком большой / 422
→ не retry бесконечно
→ вернуть понятную ошибку provider-а
→ автоматического fallback в Docling/RAG нет
```

#### Доступ к файлам

Использовать файл может тот же API-user/client, который его загрузил.

По умолчанию идентификатором является `Client ID`.

Мы не переопределяем `X-Client-ID` без необходимости: backend загружает и использует runtime-файлы одним и тем же GigaChat client.

#### Удаление runtime-файлов

GigaChat предоставляет:

```text
POST /files/{file}/delete
```

Поэтому `Attachment` хранит:

```text
gigachat_file_id
```

Перед закрытием тикета backend удаляет remote runtime-файлы из GigaChat File Storage;
локальный оригинал остаётся в собственном storage для истории/админской проверки.
Если remote cleanup не удался, закрытие не выполняется и пользователь получает ошибку.

Если администратор выполняет hard delete ошибочного чата, удаляем:

```text
local attachment
+
gigachat_file_id через /files/{file}/delete
```

если remote-файл ещё существует.

Документация:

- https://developers.sber.ru/docs/ru/gigachat/guides/working-with-files

### Изображения / Vision

Screenshot — стандартный attachment любого пользовательского сообщения, но для retrieval он требует отдельного preprocessing-step.

Если пользователь прикладывает screenshot, backend **сначала отдельным GigaChat-вызовом превращает изображение в текстовый контекст**, и только после этого выполняет RAG.

Локальный OCR не используется.

Flow:

```text
USER MESSAGE + SCREENSHOT
        ↓
upload screenshot via GigaChat Files API
        ↓
CALL #0 — screenshot parse / OCR + visual analysis
        ↓
structured screenshot context
        ↓
current user text
+ parsed screenshot
+ recent dialog history
        ↓
BGE-M3
        ↓
Qdrant hybrid retrieval
        ↓
rag_top_k evidence
        ↓
    ONE GenerationContext
        ↓
    CALL #1 — structured ConfidenceAssessment
        ↓
    threshold / clarification policy
        ├── confidence >= threshold → CALL #2 user answer stream → SSE
        └── confidence < threshold → clarification или operator_support
```

Для screenshot parsing используем отдельный structured contract, например:

```python
class ScreenshotAnalysis(BaseModel):
    extracted_text: str
    visual_summary: str
```

Пример результата:

```json
{
  "extracted_text": "Поле «Организация» не заполнено. Код ошибки ...",
  "visual_summary": "Открыта форма документа 1С; обязательное поле «Организация» подсвечено."
}
```

В MVP пользовательское сообщение может содержать до 10 вложений, но не более одного изображения. Поэтому единственный screenshot проходит отдельный parse, а документы передаются в confidence и user-answer generation-вызовы. Ограничение «одно изображение на message» дополнительно соблюдается адаптером GigaChat.

Задача CALL #0:

- извлечь текст с изображения;
- определить код/текст ошибки;
- распознать важные элементы интерфейса;
- сформировать краткий visual summary;
- **не** пытаться давать финальное решение пользователю.

Retrieval-query:

```text
prompt_query =
    current user message
    + recent dialog history

screenshot_query =
    screenshot.extracted_text
    + screenshot.visual_summary
```

После этого обычный RAG:

```text
BGE-M3(prompt_query) dense + sparse → Qdrant
BGE-M3(screenshot_query) dense + sparse → Qdrant
→ dense preflight threshold 0.35
→ Qdrant RRF
→ equal-weight application RRF по rank/vector_id
→ deduplication
→ rag_top_k
```

Confidence/answer flow использует уже полный контекст:

```text
system prompt
recent dialog history
current user message
screenshot analysis
original screenshot file_id
RAG evidence
operator_escalation_threshold
```

Сам screenshot можно повторно передать в confidence и user-answer generation-вызовы
через уже загруженный `file_id`.

Итого:

```text
обычный turn:
CALL #1 ConfidenceAssessment
CALL #2 user answer stream

turn со screenshot:
CALL #0 screenshot parse
CALL #1 ConfidenceAssessment
CALL #2 user answer stream
```

Все GigaChat-вызовы выполняются последовательно под единым re-entrant `GenerationGate`.

### Финальный prompt

Используем стабильную структуру, а не набор скрытых последовательных LLM-вызовов.

```text
SYSTEM
{active_system_prompt}

CURRENT SETTINGS
operator_escalation_threshold = {operator_escalation_threshold}

DIALOG CONTEXT
{recent_dialog_history}

USER QUESTION
{question}

KNOWLEDGE EVIDENCE
[S1] {chunk}
[S2] {chunk}
...

INSTRUCTIONS
1. Определи проблему пользователя.
2. Сопоставь проблему с KNOWLEDGE EVIDENCE.
3. Дай конкретные пошаговые действия.
4. Используй evidence для проверки утверждений; внутренние labels источников не
    раскрывай пользователю.
5. Не придумывай отсутствующие пункты меню, версии и причины ошибок.
6. Если evidence недостаточно — снижай confidence.
7. Первый user call возвращает только structured `ConfidenceAssessment`.
8. Второй user call возвращает обычный Markdown-текст без JSON и служебных статусов.
9. Явная просьба оператора обрабатывается backend до LLM pipeline.
```

Системная часть user answer не захардкожена в коде и берётся из
`SystemPrompt(type=user_support)`. Единственное исключение — техническая
confidence-инструкция: она намеренно захардкожена в backend и не является
пользовательским prompt.

Для трёх независимых задач:

```text
SystemPrompt(type=user_support)
SystemPrompt(type=operator_gigachat)
SystemPrompt(type=knowledge_card)
```

Промпты хранятся в PostgreSQL, редактируются администратором и применяются без
рестарта. `operator_gigachat` используется для ручного шаблона ответа, а
`knowledge_card` — кнопкой заполнения карточки и для explicit legacy/admin backfill.
Новые candidates получают deterministic initial card.

System Prompt:

- не проходит через Docling;
- не индексируется BGE-M3;
- не хранится в Qdrant;
- напрямую подставляется в `SYSTEM`.

### LangChain-first: основной способ разработки backend

**Ключевое архитектурное правило проекта:**

> Вся LLM-логика backend в первую очередь реализуется через `langchain-gigachat` и стандартные abstractions LangChain Core. Прямое использование REST API GigaChat или низкоуровневого пакета `gigachat` допускается только если нужная возможность отсутствует в `langchain-gigachat`.

`langchain-gigachat` — официальный/партнёрский LangChain integration package для GigaChat. Он оборачивает Python SDK `gigachat` и предоставляет LangChain-совместимые интерфейсы.

То есть основные application-services не должны знать про:

```text
POST /chat/completions
POST /files
OAuth HTTP request
raw SSE parsing
raw GigaChat request/response DTO
```

Они работают через LangChain primitives.

Базовый слой:

```text
FastAPI services
    ↓
LangChain Core / LCEL
    ↓
langchain-gigachat
    ↓
gigachat Python SDK
    ↓
GigaChat API
```

#### Версии для MVP

Ориентируемся на актуальную ветку `langchain-gigachat 0.5.x`.

Минимально:

```text
Python >= 3.10
langchain-core >= 1,<2
langchain-gigachat >= 0.5.1,<0.6
```

Ветка `0.5.x` использует `gigachat >= 0.2,<0.3` как underlying SDK и Pydantic V2.

Версии фиксируем в lock-файле проекта, чтобы поведение интеграции не менялось во время хакатона.

#### Что используем из LangChain Core

Основные primitives:

```text
SystemMessage
HumanMessage
AIMessage
ChatPromptTemplate
Runnable / LCEL
Pydantic models
```

Основной runtime pipeline остаётся простым:

```text
Input
↓
ContextBuilder
↓
Retriever
↓
PromptBuilder
↓
ChatGigaChat / GigaChat
↓
Structured Output parser
```

Не используем тяжёлый AgentExecutor, multi-agent orchestration или LangGraph там, где достаточно обычной LCEL/Runnable-цепочки.

#### Инициализация GigaChat через LangChain

Application-код создаёт модель через:

```python
from langchain_gigachat import GigaChat

llm = GigaChat(
    model=active_model,
    max_tokens=gigachat_max_output_tokens,
    ca_bundle_file=GIGACHAT_CA_BUNDLE_FILE,
    max_retries=3,
    retry_backoff_factor=0.5,
)
```

Credentials/scope предпочтительно задаются environment variables:

```text
GIGACHAT_CREDENTIALS
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_CA_BUNDLE_FILE
```

Модель (`model`) и `max_tokens` берутся из runtime settings PostgreSQL. Администратор
сохраняет через один PUT модель, context ratios, `max_tokens`, `rag_top_k` и threshold;
backend валидирует их и применяет к следующим generation-вызовам.

#### Синхронный и асинхронный API

В FastAPI основной путь — async:

```python
response = await llm.ainvoke(messages)
```

Для streaming:

```python
async for chunk in llm.astream(messages):
    ...
```

Не используем старые `predict()` / `apredict()` — в `langchain-core 1.x` они удалены.

Для обычных unit-тестов допустим:

```python
llm.invoke(...)
llm.stream(...)
```

#### Messages вместо ручного payload

История диалога преобразуется в стандартные LangChain messages:

```python
messages = [
    SystemMessage(content=system_prompt),
    HumanMessage(content="..."),
    AIMessage(content="..."),
    HumanMessage(content="..."),
]
```

`ContextBuilder` отвечает только за то, **какие** последние сообщения попадут в список.

Формирование JSON для GigaChat API оставляем `langchain-gigachat`.

#### Structured Output через `with_structured_output`

Structured Output используется для **Call #1 — confidence текущего контекста**:

```python
class ConfidenceAssessment(BaseModel):
    confidence: float = Field(ge=0, le=1)

assessment = llm.with_structured_output(
    ConfidenceAssessment,
    method="json_schema",
)

confidence = await assessment.ainvoke(confidence_messages)
```

Confidence call выполняется до **Call #2** обычным `llm.astream(...)`. Он получает
hardcoded technical prompt, а не редактируемый `SystemPrompt(type=user_support)`.
Если threshold достаточный, chunks user answer сразу отправляются через SSE; иначе
Call #2 не запускается, а decision policy выбирает clarification или
`operator_support`.

Screenshot parse и явное заполнение Knowledge Card также используют отдельные
structured schemas внутри `GigaChatProvider`.

Fallback `json_schema → function_calling` остаётся локальной деталью `GigaChatProvider`, если выбранная модель не принимает native `response_format`.

#### Attachments через LangChain content blocks

Для screenshot/document используем стандартный LangChain `HumanMessage` с `content_blocks`.

Явная загрузка файла:

```python
uploaded = await llm.aupload_file(
    ("screenshot.png", file_bytes)
)
```

Сообщение:

```python
HumanMessage(
    content_blocks=[
        {
            "type": "text",
            "text": question,
        },
        {
            "type": "image",
            "file_id": uploaded.id_,
        },
    ]
)
```

Для документов:

```text
type = "file"
```

Поддерживаемые типы wrapper-а:

```text
image
audio
file
```

В нашем MVP нужны:

```text
image
file
```

`auto_upload_attachments=True` умеет автоматически загружать base64/data URL, но в production/MVP предпочитаем **явный `upload_file()/aupload_file()`**, чтобы контролировать lifecycle файла и сохранять `gigachat_file_id`.

Файловые операции также доступны прямо через `langchain-gigachat`:

```text
upload_file / aupload_file
list_files / alist_files
get_file / aget_file
get_file_content / aget_file_content
delete_file / adelete_file
```

Следовательно отдельный прямой REST-клиент Files API нам не нужен.

#### Streaming

Streaming используется для user answer и ручного operator template:

```python
async for chunk in llm.astream(answer_messages):
    ...
```

Confidence-call выполняется через structured `ainvoke()` и возвращает маленький
Pydantic-объект до запуска user answer. User answer выполняется через `astream()`;
его chunks не буферизуются перед публикацией.

FastAPI транслирует обычные текстовые chunks через SSE.

Поэтому не нужен incremental JSON parser:

```text
Call #1 → structured ConfidenceAssessment → backend threshold decision
Call #2 → plain text SSE → frontend
manual template → plain text HTTP response → frontend
```

#### Retry: только в одном слое

`langchain-gigachat` прокидывает настройки retry underlying `gigachat` SDK:

```python
GigaChat(
    max_retries=3,
    retry_backoff_factor=0.5,
)
```

SDK по умолчанию умеет повторять временные ошибки, включая:

```text
429
500
502
503
504
```

**Не включаем одновременно:**

```text
GigaChat(max_retries=3)
+
llm.with_retry(...)
```

Иначе число попыток перемножается.

Для MVP retry настраиваем только через параметры `GigaChat(...)`.

#### Ошибки

`langchain-gigachat` не прячет исключения underlying SDK.

На границе `GigaChatProvider` обрабатываем типизированные ошибки, например:

```text
AuthenticationError
RateLimitError
BadRequestError
ForbiddenError
NotFoundError
RequestEntityTooLargeError
ServerError
GigaChatException
```

Остальная бизнес-логика получает уже наши внутренние provider errors.

То есть SDK-specific exceptions не должны расползаться по `DialogService`, `RAGService` и API endpoints.

#### `X-Session-ID` и request tracing

Underlying SDK поддерживает:

```text
session_id_cvar  → X-Session-ID
request_id_cvar  → X-Request-ID
```

Так как `langchain-gigachat` построен поверх этого SDK, настройку технических headers инкапсулируем внутри `GigaChatProvider`.

На каждый диалог:

```text
X-Session-ID = Dialog.id
```

На каждый generation request:

```text
X-Request-ID = uuid4()
```

Wrapper также сохраняет provider tracing metadata:

```text
AIMessage.id → x-request-id
ChatResult.llm_output["x_headers"]
```

Это можно писать в технический лог для диагностики без ручного разбора HTTP headers.

#### Tool calling

В MVP tool calling **не нужен для основного support pipeline**.

Если он понадобится позже, для нового кода используем только стандартный LangChain API:

```python
from langchain_core.tools import tool

llm.bind_tools(...)
```

Не используем legacy `bind_functions()`.

Ограничение GigaChat:

```text
parallel tool calls не поддерживаются
```

Поэтому даже в Roadmap проектируем максимум один tool call за один assistant turn.

#### GigaChatEmbeddings не используем

`langchain-gigachat` содержит:

```python
GigaChatEmbeddings
```

но в нашем проекте **он запрещён архитектурным решением MVP**.

Причина: embeddings GigaChat — отдельный API/тарификация, а у нас уже выбран локальный:

```text
BAAI/bge-m3
```

Поэтому:

```text
Generation / Vision / files
→ langchain-gigachat.GigaChat

Embeddings / retrieval
→ local BGE-M3 + Qdrant
```

Нельзя случайно заменить `BGE-M3` на `GigaChatEmbeddings` только потому, что такой класс есть в библиотеке.

#### Что разрешено делать напрямую через `gigachat` SDK

По умолчанию — ничего в application/business code.

Если в будущем `langchain-gigachat` не предоставляет конкретную новую API-возможность GigaChat, допускается локальный fallback **только внутри `GigaChatProvider`**:

```text
app/services/*
    ✕ from gigachat import ...

app/providers/gigachat_provider.py  # LangChain-first wrapper над langchain-gigachat
    ✓ при доказанной необходимости
```

Перед добавлением прямого SDK-вызова нужно сначала проверить, нет ли эквивалента в текущей версии `langchain-gigachat`.

Таким образом зависимость направлена строго:

```text
Business logic
    ↓
LangChain abstractions
    ↓
GigaChatProvider
    ↓
langchain-gigachat
    ↓
gigachat SDK (implementation detail)
```

### Простая проверка RAG

RAG проверяем отдельно от generation:

```text
tests/rag/rag_golden.json
tests/rag/evaluate_rag.py
```

Минимум 10–20 вопросов с ожидаемым документом.

Скрипт выполняет тот же retrieval, что production-код, и показывает:

```text
OK / FAIL
expected document in top-3
```

Без LangSmith/RAGAS и отдельной evaluation-инфраструктуры в MVP.

## 14. Скриншоты и runtime attachments

Скриншоты и документы — стандартное вложение любого сообщения, а не отдельный пользовательский режим.

Изображение не является отдельным режимом. Кнопка прикрепления screenshot доступна **в каждом обычном диалоге**.

MVP: PNG/JPEG/TIFF/BMP, один screenshot на пользовательский turn.

### Runtime

```text
Пользователь:
"Что делать?" + screenshot
        ↓
        ↓
"Поле Организация не заполнено..."
        ↓
BGE-M3 dense+sparse
        ↓
Qdrant hybrid retrieval
        ↓
[S1] инструкция по заполнению...
[S2] похожий решённый случай...
        ↓
GigaChat (модель задана backend-политикой)
INPUT:
- "Что делать?"
- исходный screenshot
- [S1], [S2]
        ↓
OUTPUT:
confidence → threshold → streaming answer или clarification/operator
```

Screenshot preprocessing нужен для того, чтобы до confidence/answer generation найти
документы по тексту ошибки. Source labels используются внутри backend и не выдаются
текущим frontend DTO/UI.

При плохом качестве изображения:

- если evidence и визуальные данные недостаточны — пользователь получает понятный запрос прислать более чёткий screenshot либо обращение эскалируется оператору.

## 15. Внешние каналы Bitrix24/Redmine — Roadmap

AI GigaChat оператора в собственном web-интерфейсе входит в текущий lifecycle. Roadmap относится именно к подключению внешних каналов через adapters.

> **Статус:** сценарий предусмотрен архитектурой, но **не входит в обязательный MVP первого этапа**. Фокус MVP — работающий Q&A-чат, RAG, Vision и управление БЗ.

После хакатона:

- `Integration Gateway` подписывается на события Bitrix24 Open Lines или получает сообщения Redmine HelpDesk;
- входящие данные нормализуются в тот же `IncomingMessage`, который использует собственный frontend;
- сообщение проходит существующий `Dialog Service` → `RAG/Vision` → `Escalation`;
- `suggest` — AI генерирует черновик ответа для оператора;
- `auto` — при достаточной уверенности ответ отправляется автоматически;
- при низкой уверенности обращение передаётся оператору.

Ключевое требование уже сейчас: **не связывать бизнес-логику с нашим frontend**, чтобы позднее этот сценарий добавлялся через адаптер, а не через переписывание ядра.

## 16. Модель данных

MVP-модель оставляем минимальной: каждая сущность либо участвует в runtime-flow, либо нужна одной из трёх frontend-панелей.

| Сущность             | Ключевые поля                                                                                                                                                                                                                                                                  | Назначение / frontend                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `User`               | `id`, `role`, `display_name`                                                                                                                                                                                                                                                   | Авторизация и role guards: `user / operator / admin`                                                                                |
| `Dialog`             | `id`, `user_id`, `status`, `mode`, `channel`, `dialog_confidence`, `assigned_operator_id?`, `escalated_at?`, `closed_at?`, `created_at`, `updated_at`                                                                                                                          | Сам тикет. `Dialog` одновременно является пользовательским обращением и операторским тикетом                                        |
| `DialogFeedback`     | `id`, `dialog_id`, `verdict`, `created_at`                                                                                                                                                                                                                                     | Финальная оценка закрытого Dialog: `helpful / ai_error`; отсутствие записи = «ожидает оценки»                                       |
| `Message`            | `id`, `dialog_id`, `author_type`, `text`, `confidence?`, `sources?`, `processing_status?`, `processing_error?`, `created_at`                                                                                                                                                   | Сообщения `user / assistant / operator / system`; состояние user trigger-turn сохраняется для восстановления генерации после reload |
| `Attachment`         | `id`, `message_id`, `storage_key`, `mime_type`, `gigachat_file_id?`, `extracted_text?`, `visual_summary?`, `remote_deleted_at?`                                                                                                                                                | Runtime screenshot/document + результат screenshot parse                                                                            |
| `KnowledgeSection`   | `id`, `name`, `is_enabled`, `created_at`                                                                                                                                                                                                                                       | Раздел БЗ и master switch                                                                                                           |
| `KnowledgeDocument`  | `id`, `section_id`, `source_type`, `title`, `storage_key`, `one_c_version?`, `tags`, `is_enabled`, `index_status`, `index_error?`, `indexed_at?`                                                                                                                               | `one_c_version` — версия конфигурации 1С, не история правок документа; версионирование файла остаётся Roadmap                       |
| `Chunk`              | `id`, `doc_id`, `text`, `vector_id`, `metadata`                                                                                                                                                                                                                                | Внутренний RAG-фрагмент, напрямую frontend не редактирует                                                                           |
| `KnowledgeCandidate` | `id`, `dialog_id`, `source`, `generated_card`, `status`, `resulting_document_id?`, `reviewed_by?`, `reviewed_at?`                                                                                                                                                              | `UNIQUE(dialog_id)`; после Approve `resulting_document_id → KnowledgeDocument.id`                                                   |
| `SystemPrompt`       | `id`, `type`, `content`, `updated_at`, `updated_by`                                                                                                                                                                                                                            | Одна редактируемая запись на каждый prompt: `user_support / operator_gigachat / knowledge_card`                                     |
| `SystemSetting`      | `key`, `value`, `updated_at`                                                                                                                                                                                                                                                   | Runtime AI/RAG settings без restart                                                                                                 |
| `MetricEvent`        | `id`, `dialog_id?`, `event_type`, `success`, `error_message?`, `latency_ms`, `confidence?`, `escalated`, `prompt_tokens?`, `completion_tokens?`, `precached_prompt_tokens?`, `gigachat_model?`, `system_prompt?`, `rag_top_k?`, `operator_escalation_threshold?`, `created_at` | Один aggregate на user turn: полная latency цепочки и суммарный usage confidence + answer calls |

### DB constraints / delete rules

```text
KnowledgeCandidate.dialog_id
→ UNIQUE
→ FK Dialog.id ON DELETE CASCADE

KnowledgeCandidate.resulting_document_id
→ nullable FK KnowledgeDocument.id
→ ON DELETE SET NULL

Message.dialog_id
→ FK Dialog.id ON DELETE CASCADE

Attachment.message_id
→ FK Message.id ON DELETE CASCADE

DialogFeedback.dialog_id
→ FK Dialog.id ON DELETE CASCADE
```

Candidate создаётся для каждого нового закрытого Dialog в той же транзакции, что и
закрытие. Для старых данных и legacy admin-пути используется idempotent service method:

```python
def create_or_get_candidate(dialog_id, source):
    existing = repo.get_by_dialog_id(dialog_id)
    if existing:
        return existing

    return repo.create(
        dialog_id=dialog_id,
        source=source,
        status="pending",
    )
```

`source` фиксирует **первый источник создания** и не перезаписывается повторным get-or-create.

### Что убираем из MVP-модели

Отдельные сущности:

```text
Escalation
Ticket
OperatorSystemPrompt
```

не нужны.

Причины:

```text
Escalation
→ состояние уже выражается через:
Dialog.mode = operator_support
assigned_operator_id
escalated_at

Ticket
→ сам Dialog является тикетом;
external_id понадобится только при подключении Bitrix24/Redmine

OperatorSystemPrompt
→ дублировал SystemPrompt;
различаем prompts полем SystemPrompt.type
```

Для будущих Bitrix24/Redmine при необходимости добавляется отдельный `ExternalChannelBinding`, не меняя `Dialog`.

### Enum conventions

```text
User.role:
user
operator
admin

Dialog.status:
active
closed

Dialog.mode:
ai_support
operator_support

Dialog.channel:
web
bitrix24
redmine

Message.author_type:
user
assistant
operator
system

DialogFeedback.verdict:
helpful
ai_error

KnowledgeCandidate.status:
pending
approved
rejected

KnowledgeCandidate.source:
user_feedback
operator
admin

KnowledgeDocument.source_type:
official_1c_docs
internal_kb
resolved_case

KnowledgeDocument.index_status:
uploaded
processing
indexed
failed

SystemPrompt.type:
user_support
operator_gigachat
knowledge_card
```

## 17. Что сознательно не усложняем

На MVP **не нужны автоматически**:

- отдельная vector DB на каждый раздел;
- knowledge graph;
- multi-agent RAG;
- LLM query rewriting отдельным вызовом;
- отдельный reranker;
- fine-tuning embedding-модели.

Если golden dataset покажет, что hybrid BGE-M3 + Qdrant не даёт нужный Recall@k, первым улучшением будет локальный reranker поверх top-20, а не усложнение всей архитектуры.

# Часть III — Frontend

Frontend — одно **React SPA** с тремя изолированными role-зонами. Отдельные приложения не создаём.

```text
React 18
TypeScript
Vite
Tailwind CSS
React Router v7
React Query (`@tanstack/react-query`)
```

Принцип:

```text
REST + React Query
→ server state / mutations

SSE
→ realtime events / streaming

local component state
→ textarea, modal, selected tab, streaming buffer
```

Redux/Zustand в MVP не нужны.

Для Tailwind используем Vite-интеграцию; отдельный config-файл добавляем только если появится реальная theme/plugin-настройка. Базовые стили подключаются через общий `src/index.css`.

## 18. Общая frontend-архитектура

### 18.1 Три панели

```text
/user
/operator
/admin
```

В одном SPA:

```text
Root
├── UserLayout
├── OperatorLayout
└── AdminLayout
```

Каждая role-зона является отдельным feature-модулем. Переиспользуются только:

```text
shared UI
chat primitives
API client
DTO/types
query keys
auth/session
```

Внутренние компоненты `admin` не импортируются напрямую в `operator`, и наоборот.

### 18.2 Routing — React Router v7

Используем `createBrowserRouter` + nested layouts + `<Outlet />`.

Server data остаётся в React Query; не дублируем REST-fetch одновременно в React Router loaders и React Query.

Карта routes:

```text
/
├── /user
│   ├── index
│   └── /dialogs/:dialogId
│
├── /operator
│   ├── index
│   └── /dialogs/:dialogId
│
└── /admin
    ├── /dialogs
    │   └── /:dialogId
    ├── /knowledge
    │   └── /documents/:documentId
    ├── /prompts
    ├── /settings
    └── /monitoring
```

`/user`, `/operator`, `/admin` защищаются role guard.

### 18.3 Auth и role guards

Frontend bootstrap:

```text
GET /api/me
```

Ответ:

```ts
type CurrentUser = {
  id: string;
  role: "user" | "operator" | "admin";
  displayName: string;
};
```

Role guard отвечает только за UX/navigation. Backend повторно проверяет role на каждом endpoint.

Для SPA + native `EventSource` предпочтительно same-origin auth через **HttpOnly Secure cookie**. GigaChat credentials никогда не попадают в browser.

Dev:

```text
Vite /api proxy
→ FastAPI
```

Prod:

```text
SPA + /api
→ один origin
```

### 18.4 React Query

React Query — единственный cache/server-state слой frontend.

Централизованные query keys:

```ts
queryKeys.me();

queryKeys.user.dialogs();
queryKeys.dialog.detail(dialogId);
queryKeys.dialog.messages(dialogId);

queryKeys.operator.queue(scope);
queryKeys.kb.sections();
queryKeys.kb.documents(filters);
queryKeys.kb.document(documentId);

queryKeys.admin.dialogs(filters);
queryKeys.admin.candidate(dialogId);

queryKeys.prompts();
queryKeys.settings();
queryKeys.monitoring(period);
```

После mutation используем **targeted invalidation**, а не `invalidateQueries()` всего приложения. Query key обязан однозначно описывать ресурс и его параметры.

Примеры:

```text
close dialog
→ dialog detail
→ user dialogs
→ operator queue
→ admin journal

toggle document
→ current document
→ documents list
→ section summary

approve candidate
→ candidate
→ admin dialog list
→ knowledge documents
```

Streaming token не записываем в Query Cache на каждый chunk.

### 18.5 API client

Все HTTP-вызовы идут через typed layer:

```text
src/api/
├── client.ts
├── queryKeys.ts
├── auth.ts
├── dialogs.ts
├── operator.ts
├── knowledge.ts
├── admin.ts
├── settings.ts
└── monitoring.ts
```

Компоненты не вызывают `fetch()` напрямую.

Нормализованная ошибка:

```ts
type ApiError = {
  code: string;
  message: string;
  details?: unknown;
};
```

### 18.6 DTO из backend

Frontend напрямую использует:

```text
User
Dialog
DialogFeedback
Message
Attachment
OperatorTemplateDto
KnowledgeSection
KnowledgeDocument
KnowledgeCandidate
SystemPrompt
SystemSetting
```

`Chunk`, `SourceRef` и `MetricEvent` являются backend/internal сущностями: frontend
получает не raw row, а агрегированный `MonitoringResponse`. Source snapshot хранится
в `Message.sources`, но текущий public/admin message contract его не отдаёт.

Минимальные frontend DTO:

```ts
type DialogStatus = "active" | "closed";
type DialogMode = "ai_support" | "operator_support";
type MessageAuthor = "user" | "assistant" | "operator" | "system";
type FeedbackVerdict = "helpful" | "ai_error";

type SourceRef = {
  documentId: string;
  title: string;
  label: string; // internal only
  page?: number;
  headingPath?: string[];
};

type DialogSummary = {
  id: string;
  status: DialogStatus;
  mode: DialogMode;
  confidence: number;
  assignedOperator?: {
    id: string;
    displayName: string;
  };
  lastMessagePreview?: string;
  updatedAt: string;
};

type MessageDto = {
  id: string;
  dialogId: string;
  authorType: MessageAuthor;
  text: string;
  confidence?: number;
  attachments: AttachmentDto[];
  createdAt: string;
};
```

`SourceRef` и `Message.sources` остаются внутренними полями retrieval/audit; отдельный
source list/citation component в текущем frontend не реализован.

После стабилизации FastAPI OpenAPI желательно генерировать TS-types/client, чтобы не дублировать enum вручную.

### 18.7 Общие UI primitives

```text
Button
Input
Textarea
Select
Slider
Switch
Tabs
Badge
Card
Table
Modal
ConfirmDialog
Toast
Skeleton
EmptyState
ErrorState
```

Chat primitives:

```text
MessageList
MessageBubble
AttachmentCard
AttachmentPreview
ChatComposer
StreamingMessage
SystemMessage
DialogStatusBadge
```

Базовые UI-компоненты не содержат domain logic.

### 18.8 Общие UX-правила

Для каждого server screen:

```text
loading
success
empty
error
```

Mutation:

- блокирует повторный submit;
- показывает pending;
- destructive action всегда через `ConfirmDialog`.

Клавиатура chat composer:

```text
Enter       → send
Shift+Enter → newline
```

После send focus возвращается в textarea.

---

## 19. SSE и взаимодействие с backend

### 19.1 Почему streams разделены по ролям

Операторский stream изолирован от пользовательского: пользователь не получает
события рабочего места оператора.

Поэтому streams разделены:

```text
USER:
GET /api/dialogs/:dialogId/events

OPERATOR QUEUE:
GET /api/operator/events

OPERATOR DIALOG:
GET /api/operator/dialogs/:dialogId/events
```

Backend авторизует каждый stream по роли и Dialog access.

### 19.2 User SSE events

```ts
type UserDialogEvent =
  | { type: "confidence"; value: number }
  | { type: "operator_connected"; operator?: UserRef; message: MessageDto }
  | { type: "assistant_token"; token: string }
  | { type: "assistant_done"; message: MessageDto }
  | { type: "operator_message"; message: MessageDto }
  | { type: "dialog_closed" }
  | { type: "error"; message: string };
```

Числовой confidence пользовательскому UI показывать не обязательно; событие используется для состояния turn.

`operator_connected.message` — уже сохранённый backend system `Message`. Frontend рендерит именно его, а не создаёт локальную псевдозапись. После reload тот же message приходит из обычной истории `/messages`.

### 19.3 Operator queue SSE

```ts
type OperatorQueueEvent =
  | { type: "ticket_available"; dialog: DialogSummary }
  | { type: "ticket_claimed"; dialogId: string; operator: UserRef }
  | { type: "ticket_closed"; dialogId: string };
```

Queue обновляется сразу, без постоянного polling.

### 19.4 Operator dialog SSE

```ts
type OperatorDialogEvent =
  | { type: "user_message"; message: MessageDto }
  | { type: "dialog_closed" }
  | { type: "error"; message: string };
```

Шаблон не передаётся через SSE: endpoint генерации возвращает готовый
`OperatorTemplateDto` в обычном HTTP-ответе.

### 19.5 Streaming cache strategy

На token events держим локальный буфер:

```text
streamingAssistantText
```

Не вызываем React Query `setQueryData()` на каждый token.

Текст AI-ответа рендерится через `react-markdown` с `remark-gfm`. Блоки
кода передаются в `PrismLight` из `react-syntax-highlighter` с явным набором
зарегистрированных языков. Raw HTML от модели не включается (`skipHtml`), так
как ответ модели является недоверенным пользовательским контентом.

На:

```text
assistant_done
operator_message
```

обновляем конкретный cache entry или делаем targeted invalidation.

### 19.6 SSE reconnect

Backend присваивает каждому событию SSE `id:`.

Frontend:

- разрешает стандартный reconnect;
- после reconnect refetch текущего Dialog/queue;
- backend остаётся source of truth;
- финальные persisted `message.id` предотвращают duplicate rendering.

---

## 20. Backend API contract для frontend

OpenAPI-схема FastAPI и Swagger UI `/docs` — источник истины для frontend/backend разработки; ответственность endpoints должна сохраняться.

### 20.1 Shared / User

| Method | Endpoint                                            | Назначение                                                    |
| ------ | --------------------------------------------------- | ------------------------------------------------------------- |
| GET    | `/api/me`                                           | текущий пользователь + role                                   |
| GET    | `/api/dialogs`                                      | dialogs текущего user                                         |
| POST   | `/api/dialogs`                                      | создать новый Dialog                                          |
| GET    | `/api/dialogs/{dialogId}`                           | metadata Dialog, включая `is_processing` и `processing_error` |
| GET    | `/api/dialogs/{dialogId}/messages?cursor=&limit=50` | история сообщений                                             |
| POST   | `/api/dialogs/{dialogId}/messages`                  | отправить text + optional attachment                          |
| POST   | `/api/dialogs/{dialogId}/close`                     | пользователь закрывает AI-resolved тикет                      |
| POST   | `/api/dialogs/{dialogId}/feedback`                  | `helpful / ai_error` после close                              |
| GET    | `/api/dialogs/{dialogId}/events`                    | user-safe SSE                                                 |

Message send:

```text
multipart/form-data

client_message_id
text
attachments   # repeated, максимум 10
```

`client_message_id = UUID` нужен для idempotency/retry.

Backend возвращает persisted user `Message` сразу. В `ai_support` GigaChat processing
запускается через FastAPI `BackgroundTasks` после отправки HTTP-ответа и идёт дальше
через SSE; в `operator_support` сообщение ожидает действий оператора. При этом
backend admission не принимает новый user AI-turn, включая отправку в другом чате,
пока существует любой активный `pending/processing` AI trigger.
Так новый route успевает подключить `EventSource` до первого token event. Состояние
trigger-message (`pending / processing / completed / failed`) хранится в БД, поэтому
после reload frontend восстанавливает placeholder или показывает сохранённую ошибку
даже при потерянном SSE-событии. Списки и открытые панели дополнительно обновляются
polling-запросами.

### 20.2 Operator

| Method | Endpoint                                    | Назначение                                        |
| ------ | ------------------------------------------- | ------------------------------------------------- | ----------------------- |
| GET    | `/api/operator/dialogs?scope=unassigned     | mine`                                             | активная operator queue |
| POST   | `/api/operator/dialogs/{dialogId}/claim`    | атомарно назначить тикет текущему operator        |
| GET    | `/api/operator/events`                      | realtime queue SSE                                |
| GET    | `/api/operator/dialogs/{dialogId}/events`   | operator-only user/dialog state SSE               |
| POST   | `/api/operator/dialogs/{dialogId}/template` | сгенерировать шаблон ответа по актуальной истории |
| POST   | `/api/dialogs/{dialogId}/messages`          | отправить сообщение как operator                  |
| POST   | `/api/dialogs/{dialogId}/close`             | закрыть тикет                                     |

Claim выполняется backend атомарно:

```text
assigned_operator_id IS NULL
→ assign current operator

already assigned
→ 409 Conflict
```

Frontend не решает concurrency самостоятельно.

### 20.3 Admin — Knowledge Base

| Method | Endpoint                                               | Назначение                        |
| ------ | ------------------------------------------------------ | --------------------------------- |
| GET    | `/api/admin/knowledge/sections`                        | sections                          |
| POST   | `/api/admin/knowledge/sections`                        | создать section                   |
| PATCH  | `/api/admin/knowledge/sections/{id}`                   | rename / enable-disable           |
| DELETE | `/api/admin/knowledge/sections/{id}`                   | удалить section                   |
| GET    | `/api/admin/knowledge/documents?section_id=`           | documents, sorted by newest first |
| POST   | `/api/admin/knowledge/sections/{section_id}/documents` | upload one permanent KB file      |
| GET    | `/api/admin/knowledge/documents/{id}`                  | document detail                   |
| PATCH  | `/api/admin/knowledge/documents/{id}`                  | enable-disable / metadata         |
| POST   | `/api/admin/knowledge/documents/{id}/reindex`          | повторный ingestion               |
| DELETE | `/api/admin/knowledge/documents/{id}`                  | удалить документ + index          |

### 20.4 Admin — Prompts / Settings

| Method | Endpoint                    | Назначение                                                  |
| ------ | --------------------------- | ----------------------------------------------------------- |
| GET    | `/api/admin/prompts`        | три системных prompt                                        |
| PUT    | `/api/admin/prompts/{type}` | обновить prompt целиком                                     |
| GET    | `/api/admin/settings`       | typed AI/RAG settings + model capabilities                  |
| PUT    | `/api/admin/settings`       | атомарно сохранить модель, context/RAG settings и threshold |

`GET /api/admin/settings` должен вернуть не только values, но и вычислительные limits:

```ts
type AdminSettingsResponse = {
  activeModel: string;
  gigachatContextRatio: number;
  gigachatMaxOutputTokens: number;
  embeddingContextRatio: number;
  ragTopK: number;
  operatorEscalationThreshold: number;
  capabilities: {
    gigachatContextLimit: number;
    embeddingContextLimit: number;
  };
  availableModels: Array<{
    id: string;
    label: string;
    contextLimit: number;
  }>;
};
```

Frontend не хардкодит model context limit. PUT принимает все runtime values кроме
вычисляемых `capabilities` и списка `availableModels`; backend сохраняет их в
`SystemSetting` одной транзакцией.

### 20.5 Admin — Dialog Journal / Moderation

| Method | Endpoint                                   | Назначение                                                                                                 |
| ------ | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------- | ---------------------------- | ------------------ | ------------------------------------------------------ |
| GET    | `/api/admin/dialogs?feedback=helpful       | ai_error                                                                                                   | unrated&moderation=moderated | unmoderated&page=` | grouped closed dialogs with optional moderation filter |
| GET    | `/api/admin/dialogs/{dialogId}`            | полный audit/detail                                                                                        |
| POST   | `/api/admin/dialogs/{dialogId}/candidate`  | idempotent backfill KnowledgeCandidate для closed Dialog                                                   |
| GET    | `/api/admin/candidates/{id}`               | candidate + case card                                                                                      |
| PATCH  | `/api/admin/candidates/{id}`               | редактировать case card                                                                                    |
| POST   | `/api/admin/candidates/{id}/generate-card` | заполнить case card через GigaChat                                                                         |
| POST   | `/api/admin/candidates/{id}/approve`       | retryable approve: сохранить card, переиспользовать deterministic document и выполнить permanent ingestion |
| POST   | `/api/admin/candidates/{id}/reject`        | reject                                                                                                     |
| DELETE | `/api/admin/dialogs/{dialogId}`            | hard delete разобранного `ai_error` Dialog                                                                 |

### 20.6 Admin — Monitoring

```text
GET /api/admin/monitoring?period=today|7d|30d|all
```

Backend возвращает уже посчитанные агрегаты; frontend не вычисляет KPI из всех Dialog client-side.

---

## 21. User panel

Routes:

```text
/user
/user/dialogs/:dialogId
```

### 21.1 Layout

Desktop:

```text
┌───────────────┬──────────────────────────────────┐
│ Dialog list   │ Active dialog                    │
│               │                                  │
│ + Новый чат   │ MessageList                      │
│               │                                  │
│               │ attachments                      │
│               │                                  │
│               │ ChatComposer                     │
└───────────────┴──────────────────────────────────┘
```

Mobile:

- list → отдельный screen/drawer;
- active dialog занимает viewport.

### 21.2 Dialog list

Показываем только значимое:

```text
короткий title/preview
status
last activity
```

Status label:

```text
AI отвечает
Специалист подключён
Закрыт
```

`DialogStatusBadge` центрирует label по горизонтали и вертикали.

Не показываем user:

```text
rag_top_k
model id
prompt version
raw Qdrant score
```

### 21.3 Messages

Типы:

```text
Вы
GigaChat
ОПЕРАТОР
System
```

AI и operator визуально различаются.

System message:

```text
К обращению подключился специалист поддержки.
Обращение закрыто.
```

### 21.4 Sources

RAG evidence и source snapshots используются backend внутри confidence/answer calls и
сохраняются в `Message.sources` для аудита. Текущий `MessageDto` не содержит
`sources`, поэтому frontend пока не показывает список источников или `[S1]`-ссылки.

### 21.5 Attachment

Composer:

```text
[attach] [textarea........] [send]
```

MVP:

```text
up to 10 attachments per message, no more than 1 image
```

Frontend:

- preview/name;
- remove before send;
- basic type/size validation.

Backend повторно валидирует всё.

При screenshot локально показываем:

```text
Анализирую изображение…
```

до первого confidence/result event.

### 21.6 Send flow

AI-mode:

```text
Send
↓
POST persisted user message
↓
local message appears
↓
[screenshot → parse]
↓
one GenerationContext
↓
ConfidenceAssessment call
↓
confidence / threshold policy
↓
┌──────────────┼────────────────┐
│              │                │
answer         clarification    operator_connected
(streamed SSE)  (assistant_done)  wait operator
```

В `ai_support` composer блокируется до:

```text
assistant_done
или
operator_connected
или
error
```

Это не позволяет пользователю создать несколько конкурирующих AI-turn внутри одного
Dialog. Кроме того, `UserProcessingProvider` держит единый global busy state: пока
любой AI-turn pending/processing, UI блокирует новый чат, навигацию в другие dialogs и
отправку в них. Backend admission повторяет это правило между workers.

В `operator_support` composer обычно блокируется только на время POST, но отправка
user message также отклоняется backend, если в другом чате активен AI-turn.

### 21.7 Retry / idempotency

При network error:

- message показывает retry;
- повтор используется с тем же `client_message_id`;
- backend не создаёт duplicate Message.

### 21.8 Operator connected

После SSE:

```text
operator_connected
```

UI:

- добавляет system message;
- меняет Dialog badge;
- прекращает ожидание assistant stream текущего turn;
- оставляет тот же URL/Dialog;
- composer снова доступен.

### 21.9 Close / feedback

В `ai_support` после полученного решения пользователь может нажать:

```text
[ Завершить обращение ]
```

После `Dialog.status=closed` composer скрывается/disabled и появляется:

```text
Решение помогло?

[ Да, помогло ]
[ Нет, AI ошибся ]
```

Feedback отправляется один раз. Pending `KnowledgeCandidate` уже создан в транзакции
закрытия; feedback не создаёт и не удаляет candidate. Если AI Dialog неактивен
24 часа, этот же close-flow запускается sweeper-ом без участия пользователя.

Если тикет закрыл operator, user получает `dialog_closed` и видит тот же feedback block.

---

## 22. Operator panel

Routes:

```text
/operator
/operator/dialogs/:dialogId
```

### 22.1 Layout

Desktop:

```text
┌────────────────┬───────────────────────────┬──────────────────┐
│ Queue          │ Dialog                    │ Template panel   │
│                │                           │                  │
│ Не назначены   │ full conversation         │ editable template│
│ Мои            │                           │ status           │
│                │ operator composer         │ actions          │
└────────────────┴───────────────────────────┴──────────────────┘
```

На узком экране template panel становится drawer/tab.

### 22.2 Queue

Только:

```text
Dialog.status = active
Dialog.mode = operator_support
```

Группы:

```text
Не назначены
Мои
```

Карточка:

```text
problem preview
user
escalated time
confidence
attachment indicator
```

Queue обновляется через `/api/operator/events` и периодический 2.5-секундный refetch.

### 22.3 Claim

До claim не показываем editable operator composer.

Action:

```text
[ Взять в работу ]
```

После успешного claim:

```text
Dialog.assigned_operator_id = current user
```

Если backend вернул `409`, frontend refetch queue/detail и показывает:

```text
Тикет уже взят другим оператором.
```

### 22.4 Dialog

Оператор видит:

- всю историю user ↔ GigaChat до эскалации;
- system event подключения;
- новые user messages;
- свои сообщения;
- attachments/screenshots;
- source snapshot только внутри backend; текущий message DTO его не содержит;
- confidence history.

### 22.5 AI GigaChat template

Сценарий запускается оператором вручную:

```text
POST /api/operator/dialogs/{dialogId}/template
→ актуальная история и вложения читаются backend в момент запроса
→ GigaChat получает историю через SystemPrompt(operator_gigachat)
→ frontend получает OperatorTemplateDto
```

UI:

```text
AI GigaChat предлагает
─────────────────────
editable template text

status: loading / ready / updated / error

[ Сгенерировать шаблон ]
[ Вставить шаблон ]
[ Скопировать ]
```

Кнопка `Вставить шаблон` disabled, пока generation не завершён или текст пуст.
Редактирование шаблона происходит в локальном textarea; шаблон не отправляется
пользователю автоматически.

### 22.6 Вставка template

Если operator textarea пустой:

```text
Вставить шаблон
→ заполнить textarea
```

Если textarea уже содержит текст:

```text
Вставить шаблон
→ ConfirmDialog:
"Заменить текущий текст шаблоном?"
```

Никогда не отправлять template автоматически.

### 22.7 New user message

Operator dialog SSE:

```text
user_message
```

Новое сообщение обновляет историю и делает ранее полученный шаблон устаревшим.
Оператор вручную запускает новую генерацию, когда она нужна.

### 22.8 Send

Operator использует тот же backend message endpoint:

```text
POST /api/dialogs/:id/messages
```

Backend определяет `author_type=operator` по authenticated role.

После persisted Message:

- user stream получает `operator_message`;
- operator detail cache обновляется.

### 22.9 Close

Operator:

```text
[ Закрыть тикет ]
```

→ confirm → POST close.

После close тикет исчезает из active queue, ожидает итоговую оценку пользователя и остаётся доступен в admin journal.

---

## 23. Admin panel

Routes:

```text
/admin/dialogs
/admin/dialogs/:dialogId
/admin/knowledge
/admin/knowledge/documents/:documentId
/admin/prompts
/admin/settings
/admin/monitoring
```

Отдельный пустой dashboard не нужен.

```text
/admin
→ redirect /admin/dialogs
```

Sidebar:

```text
Журнал обращений
База знаний
System Prompts
AI Settings
Monitoring
```

### 23.1 Dialog Journal

Главный admin workbench.

Tabs:

```text
Полезные
AI ошибся
Ожидают оценки
```

Backend filters:

```text
helpful
ai_error
unrated
```

List row:

```text
problem preview
closed_at
AI / operator resolved
feedback
last confidence
attachment indicator
moderation status (after confidence)
```

Server-side pagination.

Минимальные filters:

```text
date
resolved_by = ai | operator
has_attachment
moderation = moderated | unmoderated
```

Не добавлять десятки фильтров в MVP.

### 23.2 Dialog detail

Админ видит всё, что реально помогает разбору и входит в текущий API contract:

```text
full conversation
message authors
attachments
screenshot/document attachment metadata (extracted vision fields остаются backend-only)
RAG source snapshot (backend-only; не входит в текущий `MessageDto`)
confidence history
GigaChat model snapshot
full SystemPrompt snapshot
escalation threshold snapshot, if escalated
feedback
KnowledgeCandidate status
```

Не показываем raw vector embeddings.

### 23.3 Candidate для любого closed Dialog

Каждый закрытый Dialog уже имеет candidate, созданный во время close. Admin endpoint
остаётся idempotent backfill-механизмом для данных, созданных до этого правила.

Backend использует тот же:

```python
candidate = create_or_get_candidate(
    dialog_id=dialog.id,
    source="admin",
)
```

`UNIQUE(dialog_id)` является основной гарантией отсутствия дублей; UI-проверка только отражает состояние схемы.

```text
Knowledge candidate
Карточка решения
```

Для legacy-данных backend endpoint выполняет idempotent backfill; обычная форма
создаётся сразу для любого закрытого Dialog.

Это одинаково работает для:

```text
helpful
ai_error
unrated
```

и не позволяет admin-пути создать второй candidate поверх `user_feedback`.

### 23.4 Useful / Candidate moderation

Если candidate существует, в detail показываем editable case card:

```text
Название кейса
Проблема
Результат
```

Actions:

```text
[ Заполнить через GigaChat ]
[ Approve ]
[ Reject ]
```

Approve:

```text
pending candidate
→ get/create deterministic KnowledgeDocument
→ Markdown → Docling → BGE-M3 → Qdrant
→ candidate = approved
```

Повторный approve approved-candidate — no-op. Если документ уже `indexed`, повторная
ingestion не запускается; если предыдущая попытка оставила `uploaded/processing/failed`,
документ переиспользуется и ingestion повторяется. UI показывает indexing status.

### 23.5 AI error

Для:

```text
DialogFeedback.verdict = ai_error
```

доступно:

```text
[ Удалить чат ]
```

Hard delete только через confirm:

```text
Диалог, сообщения и вложения будут удалены без возможности восстановления.
```

После success:

```text
navigate /admin/dialogs?feedback=ai_error
invalidate journal query
```

### 23.6 Unrated

Closed Dialog без `DialogFeedback`:

```text
Ожидает оценки
```

Admin может просмотреть candidate и дождаться оценки пользователя; feedback за
пользователя admin не выставляет. Legacy candidate создаётся только idempotent
backfill endpoint-ом.

---

## 24. Admin — Knowledge Base

Route:

```text
/admin/knowledge
```

Для MVP лучше один двухпанельный экран, а не отдельные страницы для каждого действия:

```text
┌──────────────────┬────────────────────────────────────┐
│ Sections         │ Documents                          │
│                  │                                    │
│ 1C Docs       ON │ [Upload]                           │
│ Internal KB   ON │                                    │
│ Old Docs     OFF │ document table                     │
└──────────────────┴────────────────────────────────────┘
```

### 24.1 Sections

Actions:

```text
Create
Rename
Enable/Disable
Delete
```

Section switch = master switch.

При OFF:

```text
Документы не меняют собственный is_enabled,
но временно не участвуют в RAG.
```

### 24.2 Documents

Table:

```text
Document
Enabled
Updated
Index status
```

`index_status`:

```text
uploaded
processing
indexed
failed
```

Actions: enable/disable; failed documents additionally show `Reindex` directly in
the status cell. Separate document detail/edit/delete UI is not part of this panel.

Upload:

```text
выбранный section
→ browser file picker
→ POST /api/admin/knowledge/sections/{section_id}/documents
→ status=processing
```

Поля source/title/version/tags не вводятся пользователем: backend выводит source из
системного раздела, title из имени файла, а tags и one_c_version оставляет пустыми.
Для processing documents React Query использует `refetchInterval` только пока есть
активная индексация. Отдельный SSE для ingestion в MVP не нужен.

Отдельная страница document detail не нужна: список показывает только документ,
enabled, compact updated date и index status; failed status содержит action для
повторной индексации. Raw chunks и служебные metadata через UI не редактируются.

---

## 25. Admin — System Prompts

Route:

```text
/admin/prompts
```

Три вкладки одной сущности `SystemPrompt`:

```text
User Support
Operator Template
Knowledge Card
```

Mapping:

```text
user_support
operator_gigachat
knowledge_card
```

UI:

```text
multiline editor
updated_at
updated_by
[ Save ]
```

Monaco/IDE editor не нужен.

Нужны:

- dirty indicator;
- warning при уходе с несохранёнными изменениями;
- mutation pending;
- success/error toast.

Изменение prompt применяется к следующим GigaChat calls; уже запущенный stream не
меняется. `knowledge_card` используется кнопкой «Заполнить через GigaChat» и для
явного legacy/admin backfill, если у старого закрытого тикета ещё нет candidate.
Structured output содержит только `title`, `problem`, `result`. Новые candidates
получают initial карточку без дополнительного LLM-вызова.

---

## 26. Admin — AI Settings

Route:

```text
/admin/settings
```

Настройки группируются, а не выводятся одной длинной формой.

### GigaChat

```text
active model
gigachat_context_ratio
gigachat_max_output_tokens
operator_escalation_threshold
```

### Retrieval

```text
embedding_context_ratio
rag_top_k
```

Controls:

```text
ratio / threshold → Slider 0–100%
max tokens        → numeric input
rag_top_k         → integer input >= 1
model             → Select
```

Рядом вычисленный preview:

```text
Контекст GigaChat: 10% → 12 800 tokens
Контекст BGE-M3:   25% → 2 048 tokens
Порог оператора:   80%
```

Числовые limits и `available_models` приходят от backend. Save всех AI settings —
одна atomic mutation; backend валидирует модель, ratios, max tokens, `rag_top_k` и
threshold, затем сохраняет их в `SystemSetting`.

---

## 27. Admin — Monitoring

Route:

```text
/admin/monitoring
```

Период:

```text
Сегодня
7 дней
30 дней
Всё время
```

KPI cards:

```text
Всего запросов
Решено AI + %
Эскалации + %
Среднее время ответа
Полезные решения + %
```

Backend возвращает агрегаты.

Frontend не загружает все Dialog ради подсчёта KPI.

Дополнительно показывается число ошибок обработки (`failed_requests`), не смешанное
с эскалациями.

---

## 28. Frontend project structure

Feature-first без лишних архитектурных слоёв:

```text
frontend/
├── src/
│   ├── app/
│   │   ├── router.tsx
│   │   ├── providers.tsx
│   │   ├── guards/
│   │   │   └── RoleGuard.tsx
│   │   └── layouts/
│   │       ├── RootLayout.tsx
│   │       ├── UserLayout.tsx
│   │       ├── OperatorLayout.tsx
│   │       └── AdminLayout.tsx
│   │
│   ├── api/
│   │   ├── client.ts
│   │   ├── queryKeys.ts
│   │   ├── auth.ts
│   │   ├── dialogs.ts
│   │   ├── operator.ts
│   │   ├── knowledge.ts
│   │   ├── admin.ts
│   │   ├── settings.ts
│   │   └── monitoring.ts
│   │
│   ├── features/
│   │   ├── user-chat/
│   │   ├── operator/
│   │   ├── admin-dialogs/
│   │   ├── admin-knowledge/
│   │   ├── admin-prompts/
│   │   ├── admin-settings/
│   │   └── admin-monitoring/
│   │
│   ├── shared/
│   │   ├── ui/
│   │   ├── chat/
│   │   ├── hooks/
│   │   │   ├── useUserDialogEvents.ts
│   │   │   ├── useOperatorQueueEvents.ts
│   │   │   └── useOperatorDialogEvents.ts
│   │   └── types/
│   │
│   ├── main.tsx
│   └── index.css
│
├── vite.config.ts
├── tsconfig.json
└── package.json
```

Не добавляем frontend `repository / use-case / domain-service` layers без реальной необходимости.

---

## 29. Frontend performance / correctness

### Lazy routes

Role-зоны и тяжёлые admin screens грузим route-level lazy.

### Messages

История сообщений:

```text
GET ...?cursor=&limit=50
```

Для длинных Dialog использовать `useInfiniteQuery`.

Virtualization не нужна до измеримой проблемы.

### Admin tables

Server-side pagination.

### Streaming

Token chunks остаются локальным state, поэтому MessageList не переписывает React Query cache на каждый token.

### Query cancellation

API client должен прокидывать `AbortSignal` из React Query в `fetch`, чтобы запросы отменялись при смене route/query.

### Same dialog ordering

Backend остаётся источником истины по порядку Message. Frontend сортирует только по server `created_at`, а не по времени локальной машины.

---

## 30. Frontend security

- Role guard не заменяет backend RBAC.
- GigaChat credentials отсутствуют в frontend.
- Не хранить auth secrets в `localStorage`.
- Operator template доступен только назначенному operator endpoint.
- Admin destructive endpoints недоступны user/operator.
- Attachment URL выдаётся backend только авторизованному пользователю с доступом к Dialog.
- Markdown/LLM answer рендерится без небезопасного raw HTML.

# Часть IV — План разработки и справка

## 31. Вертикальные срезы разработки

### Backend B1 — данные и конфигурация

PostgreSQL models, schema creation on startup, settings, system prompts, базовые CRUD.

### Backend B2 — RAG

Docling, chunking, BGE-M3, Qdrant, hybrid retrieval, `rag_top_k`, enable/disable документов и разделов, golden retrieval test.

### Backend B3 — GigaChatProvider

LangChain-first integration, auth/certificates, active model, `ainvoke`, structured output, retry/error mapping, единый re-entrant `GenerationGate`, X-Session-ID.

### Backend B4 — пользовательский Q&A

DialogService, ContextBuilder, sliding windows, RAG evidence, confidence и threshold.

### Backend B5 — attachments / screenshot preprocessing

Upload, Files API lifecycle, screenshot/document, cleanup.

### Backend B6 — operator escalation + AI GigaChat

Переключение того же Dialog в operator-mode, operator queue, отдельный prompt
шаблона и ручная генерация шаблона по актуальной истории.

### Backend B7 — feedback и модерация

`helpful | ai_error`, automatic candidate on every close, KnowledgeCandidate, Approve/Reject, очередь ошибок AI, hard delete.

### Frontend F1 — app shell + auth

React Router layouts, `/api/me`, role guards, API client, QueryClient, shared UI.

### Frontend F2 — user panel

Dialogs, messages, SSE answer stream, attachment, escalation state, close + feedback.

### Frontend F3 — operator panel

Realtime queue, claim, dialog, operator-only SSE, manual AI GigaChat template, send/close.

### Frontend F4 — admin journal

Helpful / ai_error / unrated groups, 10-item pagination, Dialog detail, automatic
candidate card edit/fill/approve/reject, hard delete error chat.

### Frontend F5 — admin KB

Sections master switches, file-picker upload into the selected section, newest-first
documents, indexing states and inline failed-document reindex.

### Frontend F6 — admin config

System Prompts, AI Settings, Monitoring.

### Integration Roadmap

После готовности web-flow подключаем `Bitrix24` и `Redmine` через `IChannelAdapter`, не меняя ядро.

## 32. Структура репозитория

```text
├── frontend/                     # React 18 + TS + Vite SPA
│   └── src/
│       ├── app/                  # router, providers, guards, layouts
│       ├── api/                  # typed REST client + query keys
│       ├── features/             # user/operator/admin feature modules
│       └── shared/               # UI/chat/hooks/types
│
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI REST + SSE
│   │   ├── core/
│   │   ├── services/
│   │   ├── providers/
│   │   ├── channels/
│   │   ├── contracts/
│   │   └── models/
├── tests/
│   └── rag/
│       ├── evaluate_rag.py
│       └── rag_golden.json
├── docker-compose.yml            # production
├── docker-compose.dev.yml        # hot reload development
├── .env.example                  # common root runtime configuration template
├── ARCHITECTURE.md
└── Problems                      # current product backlog
```

## 33. Источники

### GigaChat / GigaChain

- [GigaChain — интеграция GigaChat с LangChain](https://developers.sber.ru/docs/ru/gigachain/tools/python/langchain-gigachat)
- [GigaChain — Python SDK GigaChat, underlying layer](https://developers.sber.ru/docs/ru/gigachain/tools/python/gigachat)
- [langchain-gigachat — README/API examples](https://github.com/ai-forever/langchain-gigachat/blob/master/libs/gigachat/README.md)
- [langchain-gigachat — migration 0.5.x](https://github.com/ai-forever/langchain-gigachat/blob/master/libs/gigachat/MIGRATION.md)

Официальные разделы, прочитанные и учтённые в архитектуре:

- [Начало работы с API для физлиц](https://developers.sber.ru/docs/ru/gigachat/quickstart/ind-using-api)
- [Сертификаты НУЦ Минцифры](https://developers.sber.ru/docs/ru/gigachat/certificates?OS=debian-ubuntu)
- [Квоты и ограничения](https://developers.sber.ru/docs/ru/gigachat/limitations)
- [Выбор модели для генерации](https://developers.sber.ru/docs/ru/gigachat/guides/selecting-a-model?lang=sh)
- [Работа с историей чата и X-Session-ID](https://developers.sber.ru/docs/ru/gigachat/guides/keeping-context)
- [Потоковая генерация токенов](https://developers.sber.ru/docs/ru/gigachat/guides/response-token-streaming)
- [Structured Output / JSON Schema / Pydantic](https://developers.sber.ru/docs/ru/gigachat/guides/structured-output)
- [Работа с файлами и изображениями](https://developers.sber.ru/docs/ru/gigachat/guides/working-with-files)

Дополнительно:

- [Основная документация GigaChat API](https://developers.sber.ru/docs/ru/gigachat/guides/main)
- [Модели GigaChat](https://developers.sber.ru/docs/ru/gigachat/models/main)
- [Подсчёт токенов](https://developers.sber.ru/docs/ru/gigachat/guides/counting-tokens)
- [GigaChain — документация](https://developers.sber.ru/docs/ru/gigachain/overview)
- [GigaChain — GitHub](https://github.com/ai-forever/gigachain)

### Локальные embeddings

- [BAAI/bge-m3 — Hugging Face](https://huggingface.co/BAAI/bge-m3)
- [intfloat/multilingual-e5-base — Hugging Face](https://huggingface.co/intfloat/multilingual-e5-base)

### RAG / preprocessing

- [Docling — поддерживаемые форматы](https://docling-project.github.io/docling/usage/supported_formats/)
- [Docling Hybrid Chunking](https://docling-project.github.io/docling/concepts/chunking/)
- [Qdrant Hybrid Search](https://qdrant.tech/documentation/search/text-search/hybrid-search/)

---

_Документ подготовлен как основа для хакатон-презентации и дальнейшей реализации. Тарифы, ID моделей и ограничения GigaChat API сверяются с актуальной официальной документацией перед релизом._
