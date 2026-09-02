# Molvest 1C Support — Полная документация проекта

## 1. Описание проекта

**Molvest 1C Support** — AI-агент технической поддержки для продуктов 1С, реализованный как модульный монолит на FastAPI с SPA-фронтендом на React (Vite). Система представляет собой единую веб-платформу с тремя ролевыми панелями:

- **User Panel** — чат с AI-ботом, загрузка скриншотов/вложений, обратная связь по закрытым тикетам.
- **Operator Panel** — список тикетов, AI-черновики ответов (GigaChat), закрытие и эскалация.
- **Admin Panel** — управление промптами, настройка моделей, мониторинг метрик, аудит тикетов, модерация кандидатов в базу знаний, жёсткое удаление ошибочных тикетов.

### Ключевые фичи

- Multi-channel диалоги (Web, Bitrix24, Redmine)
- RAG (Retrieval-Augmented Generation) с векторным поиском по базе знаний
- SSE (Server-Sent Events) для real-time чата с heartbeat
- Screenshot analysis через GigaChat (извлечение текста + визуальное описание)
- Confidence scoring для auto-эскалации на оператора
- Knowledge Base ingestion из Markdown/DOCX/PDF с chunking и embedding
- Knowledge Candidates lifecycle (pending → approved/rejected → published as KB document)
- Feedback loop: пользователь → helpful → case card → KB
- Demo-auth (три предустановленных пользователя: user / operator / admin)
- Context budgeting — строгий контроль token-бюджета для GigaChat и embedding-моделей

---

## 2. Структура проекта

```
molvest-hackaton/
├── ARCHITECTURE.md              # Архитектурный контракт
├── README.md                    # Dev/prod запуск и проверки
├── docker-compose.yml           # Production-оркестрация
├── docker-compose.dev.yml       # Hot reload development
├── tests/
│   └── rag/
│       ├── evaluate_rag.py      # RAG evaluator CLI
│       └── rag_golden.json      # Golden QA pairs
├── backend/
│   ├── Dockerfile               # Python 3.11, torch CPU
│   ├── pyproject.toml           # Runtime + mypy/Ruff dependencies
│   ├── check.sh                 # Ruff + format + Mypy
│   ├── .env.example             # Env var docs
│   ├── .env                     # Active config
│   ├── .gitignore
│   ├── alembic/                 # DB migrations
│   ├── certs/                   # Russian CA certs
│   └── app/
│       ├── main.py              # FastAPI entry point
│       ├── core/                # Config, auth, db, enums, errors, constants
│       ├── models/
│       │   └── entities.py      # 12 ORM models
│       ├── contracts/
│       │   ├── schemas.py       # Pydantic DTO
│       │   └── mappers.py       # ORM → DTO
│       ├── api/
│       │   ├── router.py        # API router
│       │   ├── routes/          # 5 route modules
│       │   ├── middleware.py    # CORS, OpenAPI
│       │   ├── openapi.py       # Custom error models
│       │   ├── sse.py           # SSE formatting
│       │   └── deps.py          # DI dependencies
│       ├── providers/           # LLM, embedding, vector, storage, parser
│       └── services/            # Business logic (11 services)
└── frontend/
    ├── Dockerfile               # Node → Nginx
    ├── vite.config.ts
    ├── .env
    ├── .gitignore
    └── src/
        ├── main.tsx             # App entry
        ├── app/
        │   ├── router.tsx       # Lazy routes + guards
        │   └── root.tsx         # Layout + sidebar
        ├── api/
        │   ├── client.ts        # API client
        │   ├── auth.ts          # Auth methods
        │   └── types.ts         # TS interfaces
        └── shared/hooks/
            ├── useAuth.ts       # Auth state hook
            └── useEventSource.ts # SSE hooks (useDialogStream, useOperatorStream)
```

---

## 3. Технологии и зависимости

### Backend (Python / FastAPI)

| Технология | Назначение |
|---|---|
| Python 3.11 + FastAPI (ASGI, uvicorn) | Веб-фреймворк |
| SQLAlchemy 2.x async | ORM (engine + session_scope) |
| PyJWT | Cookie-based JWT аутентификация |
| Alembic | Миграции БД |
| Pydantic V2 | Валидация и DTO |

### AI / ML

| Технология | Назначение |
|---|---|
| GigaChat (langchain integration) | LLM: GigaChat-2/Pro/Max/3-Ultra, 128k context, streaming, screenshot analysis, confidence scoring |
| BAAI/bge-m3 (FlagEmbedding) | Embedding: 1024d dense + sparse BM25-like, 8192 context limit |
| Docling | Документ-парсер: Markdown, DOCX, PDF |

### Векторная БД и хранилище

| Технология | Назначение |
|---|---|
| Qdrant 1.15.1 (docker) | Векторное хранилище: hybrid search (dense + sparse), коллекция `knowledge_chunks` |
| Local filesystem / S3 (aioboto3) | Бинарные вложения |

### База данных

| Технология | Назначение |
|---|---|
| PostgreSQL 17 (docker) + asyncpg | Основная БД: 13 таблиц, индексы под RAG |
| SQLite | Локальная разработка (с FKS workaround) |

### Frontend (React / TypeScript)

| Технология | Назначение |
|---|---|
| React 19 + TypeScript 5.8 | UI фреймворк |
| React Router v7 | Lazy loading, RoleGuard |
| Vite 6 | Сборка |
| Native `fetch` | API клиент (без axios) |
| Native `EventSource` API | SSE real-time |

### Инфраструктура

| Технология | Назначение |
|---|---|
| Docker Compose | 4 сервиса: postgres, qdrant, backend, frontend |
| Nginx | Reverse proxy (`/api` → backend, `/` → frontend) |
| Russian CA Certs | `Russian_Trusted_Root_CA_Cert.pem` + `Russian_Trusted_Sub_Certificate.pem` для GigaChat TLS |

---

## 4. Полный файл проекта — описание каждого

### Backend

#### `backend/app/main.py`
Точка входа FastAPI-приложения. Настраивает lifespan: инициализация схемы БД → seed данных → recovery pending turns. Инициализирует TaskSupervisor для фоновых задач и корректный shutdown.

#### `backend/app/core/config.py`
Pydantic Settings: все переменные окружения (DATABASE_URL, JWT_SECRET, GIGACHAT_*, QDRANT_*, EMBEDDING_*, RAG_*, CORS_*). Дефолты: RAG_TOP_K=6, OPERATOR_ESCALATION_THRESHOLD=0.80.

#### `backend/app/core/auth.py`
JWT-аутентификация: `create_jwt_token`, `decode_jwt_token`. PyJWT с HS256, issuer=`molvest-hackaton`, audience=`molvest-users`, TTL=480 мин. Cookie: `molvest_session` (HttpOnly, Secure, SameSite=Lax).

#### `backend/app/core/database.py`
SQLAlchemy async engine + session_scope. Поддержка PostgreSQL (asyncpg) и SQLite (с FKS workaround для локальной разработки).

#### `backend/app/core/enums.py`
Domain-enum: UserRole (user/operator/admin), DialogStatus (open/closed/escalated/pending), DialogMode (rag/operator), DialogChannel (web/bitrix24/redmine), MessageAuthor (user/agent/operator/system), FeedbackVerdict (thumbs_up/down), PromptType, CandidateStatus.

#### `backend/app/core/errors.py`
7 кастомных HTTPException-subclass: NotFound, Forbidden, Conflict, ServiceUnavailable, Unprocessable, Unauthorized.

#### `backend/app/core/constants.py`
Константы: DEMO_USER_ID, DEMO_OPERATOR_ID, DEMO_ADMIN_ID, секции БЗ (faq, installation, troubleshooting).

#### `backend/app/models/entities.py`
12 ORM-моделей с UUID PK:
- **User**: username, password_hash, role, is_active, is_demo
- **Dialog**: user_id, status, mode, channel, assigned_to, claim_summary
- **Message**: dialog_id, author, role, content, type (text/attachment/evidence)
- **Attachment**: dialog_id, filename, file_url, file_size, mime_type
- **OperatorDraft**: dialog_id, operator_id, content, status
- **KnowledgeDocument**: section_id, title, doc_type, status (pending/processing/ready/failed), file_url
- **KnowledgeSection**: title, description, parent_id
- **Chunk**: doc_id, text, metadata, vector (float[]), embedding_model
- **KnowledgeCandidate**: claim, candidates, status (pending/approved/rejected)
- **DialogFeedback**: message_id, rating, comment
- **SystemPrompt**: key, version, content, is_active
- **SystemSetting**: key, value
- **MetricEvent**: метрики системы

#### `backend/app/contracts/schemas.py`
Pydantic DTO для API: 150+ строк, snake_case → camelCase mapping.

#### `backend/app/contracts/mappers.py`
Mapper-функции из ORM-моделей в DTO (Dialog → DialogResponse, Message → MessageResponse и т.д.).

#### `backend/app/api/router.py`
API Router `/api`: объединяет 5 роутеров — auth, dialogs, operator, admin, knowledge.

#### `backend/app/api/routes/auth.py`
3 эндпоинта: POST `/login`, GET `/logout`, GET `/me`. Demo-auth: GET `/demo-login?username=&role=`.

#### `backend/app/api/routes/dialogs.py`
CRUD диалогов + SSE event stream + feedback + attachments + escalation. Эндпоинты:
- POST `/dialogs` — создать диалог
- GET `/dialogs` — список (страницация)
- GET `/dialogs/{id}` — диалог + сообщения
- POST `/dialogs/{id}/messages` — текст/вложение/evidence
- DELETE `/dialogs/{id}` — удалить диалог
- GET `/dialogs/{id}/messages/sse` — SSE поток
- POST `/messages/{id}/feedback` — thumbs_up/down

#### `backend/app/api/routes/operator.py`
Operator-панель: drafts, dialog list, close, escalate. Эндпоинты:
- GET `/operator/queue` — очередь (pending, assigned)
- POST `/operator/claim/{dialog_id}` — взять в работу
- GET `/operator/drafts/sse` — SSE черновики

#### `backend/app/api/routes/admin.py`
Admin-панель: prompts, settings, monitoring, dialogs, knowledge candidates. Эндпоинты:
- GET `/admin/journal` — журнал событий
- GET `/admin/audit` — аудит-лог
- GET `/admin/moderation` — модерация (case cards)
- PATCH `/admin/settings/{key}` — runtime настройки
- GET `/admin/prompts` — шаблоны промптов

#### `backend/app/api/routes/knowledge.py`
KB ingestion: chunking, embedding, vector store, document management. Эндпоинты:
- GET `/knowledge/sections` — разделы KB
- POST `/knowledge/sections` — создать раздел
- POST `/knowledge/documents` — ингестия документа
- GET `/knowledge/documents/{id}` — статус

#### `backend/app/api/middleware.py`
CORS middleware, OpenAPI customisation.

#### `backend/app/api/openapi.py`
Custom OpenAPI schema с error response models.

#### `backend/app/api/sse.py`
SSE helpers: `format_sse(event)`, heartbeat, stream utilities.

#### `backend/app/api/deps.py`
FastAPI DI: `get_current_user`, `get_container`, `get_session`. CookieJWT-схема (OAuth2PasswordBearer с source_code="cookie").

#### `backend/app/services/dialogs.py` (~1300 строк)
Ядро системы. `DialogService`:
- `create_dialog` — создание + seed-сообщение
- `send_message` — текст/вложение/evidence, запись в БД
- `process_user_message` — основной пайплайн: контекст → RAG → LLM → SSE
- `stream_response` — streaming LLM-ответ через SSE
- `handle_feedback` — thumbs_up/down
- `get_dialog_messages` — пагинация
- `delete_dialog` — каскадное удаление

#### `backend/app/services/rag.py`
RAG service: `retrieve` — dense + sparse поиск в Qdrant (bge-m3, 1024 dims, 8192 контекст). `build_evidence` — формирование evidence (источников) для ответа LLM.

#### `backend/app/services/moderation.py`
`ModerationService`: `analyze_claim` — извлечение case card из жалобы. `find_candidates` — поиск подходящих ответов/документов.

#### `backend/app/services/broker.py`
EventBroker для SSE: in-memory pub/sub. `subscribe(channel)` → subscriber_id, `unsubscribe(subscriber_id)`, `publish(channel, event, data)`. Каналы: `dialog:{id}`, `operator:queue`, `draft:{operator_id}`. Camelize payload, heartbeat format.

#### `backend/app/services/settings.py`
RuntimeSettings (budgeting), SettingsService (DB-persisted), PromptService (versioning).

#### `backend/app/services/context.py`
`ContextBuilder`: `estimate_tokens` — оценка количества токенов (len(text)/3). `assemble_context` — сбор контекста из диалога + RAG. `trim_to_limit` — обрезка до лимита. Greedy evidence selection по убыванию релевантности.

#### `backend/app/services/container.py`
DI Container: `ApplicationContainer` — все провайдеры и сервисы связаны вместе.

#### `backend/app/services/admin.py`
`AdminService`: `get_audit_log` — аудит-записи. `get_journal` — журнал событий. Monitoring metrics.

#### `backend/app/services/seeds.py`
Seeds: demo users, default prompts, default settings, KB sections. `DEFAULT_SETTINGS`: active_gigachat_model=GigaChat-2-Pro, gigachat_context_ratio=0.10, gigachat_max_output_tokens=2048, embedding_context_ratio=0.25, rag_top_k=6, operator_escalation_threshold=0.80.

#### `backend/app/services/tasks.py`
`TaskSupervisor`: async фоновые задачи (cleanup, ingestion). Graceful shutdown (grace_seconds=10).

#### `backend/app/services/attachments.py`
`AttachmentService`: upload, extract, cleanup. Поддерживаемые runtime-вложения: до 10 файлов на сообщение, не более одного изображения за turn, изображения до 15 MB, документы до 40 MB; общий размер вложений — менее 80 MB.

#### `backend/app/services/embeddings.py`
`BgeM3EmbeddingProvider`: FlagEmbedding, hybrid dense+sparse embedding.

#### `backend/app/providers/gigachat.py`
`GigaChatProvider`: обёртка над langchain-gigachat. Streaming, structured output, function calling. Screenshot analysis (извлечение текста + визуальное описание). Confidence assessment. Error handling: 11 специализированных ошибок (Authentication, RateLimit, BadRequest, Forbidden, NotFound, PayloadTooLarge, Server, Policy).

#### `backend/app/providers/interfaces.py`
Protocol-интерфейсы: `EmbeddingProvider`, `VectorStore`, `ObjectStorage`, `LLMProvider`, Error-иерархия.

#### `backend/app/providers/vector.py`
`QdrantHybridVectorStore`: dense + sparse payload. Operations: upsert, search, delete_points, delete_document, set_document_payload.

#### `backend/app/providers/storage.py`
`ObjectStorageProvider`: `LocalObjectStorage` + `S3ObjectStorage` (через aioboto3).

#### `backend/app/providers/docling.py`
`DoclingHybridParser`: Markdown/DOCX/PDF chunking. Output: `ParsedChunk` (text, heading_path, page).

#### `backend/certs/`
Russian Trusted Root CA + Sub CA (для GigaChat TLS локальной разработки).

#### `backend/pyproject.toml`
Зависимости: FastAPI, SQLAlchemy 2.0 (async), asyncpg, Pydantic V2, langchain-gigachat, Docling, BGE-M3, aioboto3, python-multipart, PyJWT; для статической проверки используются mypy и Ruff.

#### `backend/Dockerfile`
Python 3.11-slim, torch CPU, uvicorn.

### Frontend

#### `frontend/src/app/router.tsx`
React Router v7 lazy-loading с React.lazy + Suspense. RoleGuard для ролевой навигации. RootLayout.

#### `frontend/src/main.tsx`
Точка входа React-приложения. BrowserRouter, ThemeProvider.

#### `frontend/src/app/root.tsx`
RootLayout: sidebar, role-based навигация.

#### `frontend/src/api/client.ts`
API client: cookie auth, snake_case ↔ camelCase конвертация, error normalization.

#### `frontend/src/api/auth.ts`
Auth API: me, demoLogin, logout.

#### `frontend/src/api/types.ts`
TypeScript interfaces: Role, DialogStatus, MessageAuthor, DialogMode и др.

#### `frontend/src/shared/hooks/useAuth.ts`
Auth hook: user state, refresh, logout.

#### `frontend/src/shared/hooks/useEventSource.ts`
SSE hooks: `useDialogStream`, `useOperatorStream`. Native EventSource API.

#### `frontend/vite.config.ts`
Vite proxy → backend, React plugin.

#### `frontend/Dockerfile`
Multi-stage: node build → nginx serve.

### Инфраструктура и документация

#### `docker-compose.yml`
Production-сборка 4 сервисов: postgres, qdrant, backend, frontend.

#### `docker-compose.dev.yml`
Development-сборка с Uvicorn reload, Vite HMR и отдельными volumes.

#### `ARCHITECTURE.md`
Полное архитектурное описание (4 части): модульный монолит, RAG-пайплайн, SSE, DI.

#### `tests/rag/evaluate_rag.py`
CLI для оценки RAG.

#### `tests/rag/rag_golden.json`
Golden-набор вопросов для RAG-оценки.

#### Swagger UI / ReDoc
API-контракт генерируется FastAPI и доступен на `/docs` и `/redoc`.

---

## 5. Конфигурация

### Ключевые переменные окружения (.env.example)

| Переменная | Описание | Дефолт |
|---|---|---|
| `DATABASE_URL` | PostgreSQL DSN | `postgresql+asyncpg://molvest:molvest@localhost:5432/molvest` |
| `JWT_SECRET` | Секрет для подписи JWT | `dev-secret` |
| `JWT_ALGORITHM` | Алгоритм JWT | `HS256` |
| `JWT_ISSUER` | JWT issuer | `molvest` |
| `JWT_AUDIENCE` | JWT audience | `molvest` |
| `JWT_EXPIRE_MINUTES` | TTL сессии | `480` |
| `DEMO_AUTH_ENABLED` | Demo login | `true` |
| `GIGACHAT_BASE_URL` | GigaChat API URL | `https://gigachat.devices.сатас.ru` |
| `GIGACHAT_CREDENTIALS` | Bearer token | — |
| `GIGACHAT_CERT_FILE` | CA cert path | `certs/Russian_Trusted_Sub_Certificate.pem` |
| `ACTIVE_GIGACHAT_MODEL` | Модель по умолчанию | `GigaChat-2/Pro` |
| `GIGACHAT_CONTEXT_RATIO` | Доля контекста для GigaChat | `0.10` |
| `GIGACHAT_MAX_OUTPUT_TOKENS` | Макс. токен ответа | `2048` |
| `EMBEDDING_DEVICE` | Device для BGE-M3 | `cpu` |
| `EMBEDDING_CONTEXT_LIMIT` | Лимит контекста для embedding | `8192` |
| `EMBEDDING_CONTEXT_RATIO` | Доля для embedding | `0.25` |
| `QDRANT_URL` | Qdrant endpoint | `http://localhost:6333` |
| `QDRANT_API_KEY` | Qdrant API key | (опционально) |
| `SSE_HEARTBEAT_SECONDS` | SSE heartbeat interval | `15` |
| `RAG_TOP_K` | Кандидаты для RAG | `6` |
| `OPERATOR_ESCALATION_THRESHOLD` | Confidence для эскалации | `0.80` |
| `CORS_ORIGINS` | Разрешённые origin | `http://localhost:5173,http://localhost:3000` |
| `STORAGE_BACKEND` | File storage: `local` или `s3` | `local` |

### Demo-пользователи (из constants.py)

| User ID | Role | Display Name |
|---|---|---|
| `f47ac10b-58cc-4372-a567-0e02b2c3d479` | `user` | Демо пользователь |
| `53e8b5c1-9a2d-4f6e-b8c3-1d7e5a9f0c24` | `operator` | Демо оператор |
| `8a2b5c9d-3e1f-4a6b-8c7d-2e5f9a3b1c04` | `admin` | Демо администратор |

---

## 6. API Endpoints

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | JWT в cookie |
| GET | `/api/auth/logout` | Удаление cookie |
| GET | `/api/auth/me` | Текущий пользователь |
| GET | `/api/auth/demo-login?username=&role=` | Демо-режим |

### Dialogs (Protected)
| Method | Path | Description |
|---|---|---|
| POST | `/api/dialogs` | Создать диалог |
| GET | `/api/dialogs` | Список диалогов (страницация) |
| GET | `/api/dialogs/{id}` | Диалог + сообщения |
| POST | `/api/dialogs/{id}/messages` | Текст / вложение / evidence |
| DELETE | `/api/dialogs/{id}` | Удалить диалог |
| GET | `/api/dialogs/{id}/messages/sse` | SSE поток обновлений |
| POST | `/api/messages/{id}/feedback` | thumbs_up/down |

### Operator (Operator + Admin)
| Method | Path | Description |
|---|---|---|
| GET | `/api/operator/queue` | Очередь (pending, assigned) |
| POST | `/api/operator/claim/{dialog_id}` | Взять в работу |
| GET | `/api/operator/drafts/sse` | SSE черновики |

### Admin (Admin only)
| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/journal` | Журнал событий |
| GET | `/api/admin/audit` | Аудит-лог |
| GET | `/api/admin/moderation` | Модерация (case cards) |
| PATCH | `/api/admin/settings/{key}` | Runtime настройки |
| GET | `/api/admin/settings` | Все настройки |
| GET | `/api/admin/prompts` | Шаблоны промптов |

### Knowledge (Admin)
| Method | Path | Description |
|---|---|---|
| GET | `/api/knowledge/sections` | Разделы KB |
| POST | `/api/knowledge/sections` | Создать раздел |
| POST | `/api/knowledge/documents` | Ингестия документа |
| GET | `/api/knowledge/documents/{id}` | Статус документа |

### SSE (Protected)
| Path | Description |
|---|---|
| `/api/sse/dialogs/{id}/messages` | Обновления сообщений |
| `/api/sse/operator/drafts` | Операторские черновики |

---

## 7. Архитектурные решения и обоснование

### Модульный монолит (не микросервисы)
**Решение**: Все компоненты в одном FastAPI-приложении, но разделены на модули с чёткой ответственностью.
**Обоснование**: Для хакатона/прототипа микросервисы избыточны. Модульный монолит проще разворачивать, отлаживать и тестировать. По рекомендации ARCHITECTURE.md: *"Создавайте модули, но НЕ создавайте отдельные сервисы в Kubernetes"*.

### JWT в HttpOnly cookie (не localStorage)
**Решение**: JWT-токен хранится в HttpOnly cookie `molvest_session`.
**Обоснование**: Защита от XSS-атак — JavaScript не может прочитать cookie. SameSite=Lax защищает от CSRF.

### RAG с GigaChat + Qdrant
**Решение**: Retrieval-Augmented Generation через GigaChat-2/Pro и Qdrant (dense + sparse hybrid search).
**Обоснование**: RAG позволяет отвечать на вопросы по базе знаний без дообучения модели. Hybrid search (dense + sparse) даёт лучшее качество поиска, чем только vector или только BM25.

### BGE-M3 для embedding
**Решение**: BAAI/bge-m3 через FlagEmbedding (1024d dense + sparse vector).
**Обоснование**: BGE-M3 — state-of-the-art multi-lingual embedding модель с поддержкой dense, sparse и multi-vector. Поддерживает 8192 token context window, что достаточно для технических документов 1С.

### SSE для real-time
**Решение**: Server-Sent Events через EventBroker (in-memory pub/sub).
**Обоснование**: SSE проще WebSocket для односторонней коммуникации (server → client). EventBroker — лёгкий in-memory механизм без внешних зависимостей.

### Context budgeting
**Решение**: Строгий контроль token-бюджета для GigaChat и embedding-моделей.
**Обоснование**: GigaChat имеет лимит контекста (128k tokens). Context budgeting гарантирует, что контекст (history + evidence) не превысит лимит. Greedy selection по убыванию релевантности оптимизирует качество ответа.

### DI Container
**Решение**: `ApplicationContainer` — централизованный DI-контейнер для всех провайдеров и сервисов.
**Обоснование**: Упрощает тестирование (mock-провайдеры), облегчает замену реализаций (S3 вместо local storage, Qdrant вместо другого vector store).

### Local file storage (default)
**Решение**: Local filesystem по умолчанию, S3 опционально.
**Обоснование**: Для хакатона/демо local storage проще. S3 доступен через абстрактный протокол `ObjectStorageProvider` — легко переключить.

---

## 8. Жизненный цикл приложения (lifespan)

1. **Schema init**: SQLAlchemy create_all (postgres/sqlite)
2. **Seed defaults**: demo users, default prompts, default settings, KB sections
3. **Recovery**: restore pending operator turns из БД
4. **Shutdown**: `TaskSupervisor.shutdown(grace_seconds=10)`

---

## 9. Диаграмма зависимостей

```
main.py (FastAPI)
├── container.py (ApplicationContainer)
│   ├── Settings (pydantic)
│   ├── AsyncEngine + SessionFactory (SQLAlchemy)
│   ├── GigaChatProvider (LLM)
│   ├── BgeM3EmbeddingProvider (Embeddings)
│   ├── QdrantHybridVectorStore (Vector)
│   ├── DoclingHybridParser (Documents)
│   ├── LocalObjectStorage / S3ObjectStorage
│   ├── EventBroker (SSE pub/sub)
│   ├── TaskSupervisor (background tasks)
│   ├── DialogService (core chat logic)
│   ├── RAGService (knowledge retrieval)
│   ├── ModerationService (feedback/candidates)
│   ├── KnowledgeBaseService (ingestion)
│   ├── AttachmentService (file mgmt)
│   ├── SettingsService + PromptService (config)
│   └── AdminService (admin queries)
└── Router (5 route modules)
    ├── auth → DialogService, SettingsService
    ├── dialogs → DialogService, AttachmentService, RAGService
    ├── operator → DialogService, ModerationService
    ├── knowledge → KnowledgeBaseService
    └── admin → AdminService, ModerationService, SettingsService
```

---

## 10. Архитектуры ключевых пайплайнов

### RAG Pipeline

```
Document (.md/.docx/.pdf)
  → DoclingHybridParser → ParsedChunks
  → BgeM3EmbeddingProvider → HybridEmbedding
  → QdrantHybridVectorStore → upsert
  → search (dense + sparse) → top_k chunks
  → combined with dialog context → LLM generation
```

### Dialog Flow

```
User message
  → DialogService.process_user_message()
    → ContextBuilder.build_generation_request()
    → RAGService.retrieve_chunks()
    → LLMProvider.stream_text()
    → Confidence assessment
    → confidence < threshold? → escalate to operator
    → publish to SSE (user-dialog: {id}, operator-dialog: {id})
```

### SSE Architecture

```
DialogService → EventBroker.publish(channel, payload)
                    ↓
          format_sse(event) → SSE stream
                    ↓
          Frontend EventSource → useDialogStream/useOperatorStream
```

### Knowledge Candidate Lifecycle

```
User feedback "helpful" / Operator propose / Admin create
  → KnowledgeCandidate (PENDING)
  → Admin review (Case Card edit)
  → Admin approve → Markdown document → KB ingestion (chunk + embed + upsert)
  → Admin reject → status = REJECTED
```

---

## 11. Текущий статус и рекомендации

### Текущий статус
- Backend проверяется через mypy и Ruff из `backend/.venv`
- Единственная тестовая директория — `tests/rag`
- User vertical slice: полностью рабочий (логин → диалог → отправка → SSE streaming → ответ → завершение)
- Operator panel: login и queue работают, AI draft не генерируется (блокер)
- Admin panel: все разделы UI протестированы

### Критические рекомендации (must-fix)
1. **Добавить CI/CD** — GitHub Actions с Ruff, mypy и frontend checks
2. **Бэкапы PostgreSQL** — cron-скрипт с pg_dump + S3-хранилище
3. **Бэкапы Qdrant** — периодический snapshot
4. **Исправить Operator draft** — diagnose `DialogService.process_user_message()` (task scheduling, provider execution, draft persistence, SSE delivery)

### Важные рекомендации
6. **Rate limiting** — добавить slowapi или аналог для защиты от abuse
7. **API key rotation** — для GigaChat, Qdrant, S3
8. **Healthcheck endpoints** — `/health` для postgres, qdrant, backend
9. **Structured logging** — JSON logs с correlation IDs
10. **Environment-разделение** — `.env.prod`, `.env.staging` с разными дефолтами

### Средние рекомендации
11. **Bitrix24/Redmine webhook handlers** — enum есть, но реализации нет
12. **SSE через Redis PubSub** — EventBroker сейчас in-memory, не работает при горизонтальном масштабировании
13. **OpenTelemetry tracing** — для отладки RAG и LLM calls
14. **Feature flags** — для экспериментальных моделей и функций
15. **Migration to alembic** — alembic есть, но нужно убедиться, что все изменения модели отражены в миграциях

---

*Документация создана на основе анализа проекта Molvest 1C Support. Обновлено: 2026-01-01*
