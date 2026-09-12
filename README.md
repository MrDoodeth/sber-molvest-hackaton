# Molvest GigaChat Support
## О проекте

Molvest AI Support помогает автоматизировать первую линию технической поддержки
пользователей 1С. Система ищет ответ во внутренней базе знаний, учитывает историю
диалога и может анализировать приложенные скриншоты через GigaChat Vision.

Если AI не уверен в ответе, пользователь не теряет контекст: оператор подключается
к тому же диалогу и продолжает разговор с полной историей и вложениями. После
закрытия обращения администратор может проверить результат, отредактировать
карточку решения и опубликовать её в базе знаний.

### Основные возможности

- AI-чат технической поддержки 1С.
- Hybrid RAG по постоянной базе знаний.
- Анализ скриншотов через GigaChat Vision.
- Runtime-вложения документов и изображений.
- Автоматическая эскалация оператору.
- AI-помощник оператора с редактируемым шаблоном ответа.
- Модерация закрытых обращений.
- Пополнение базы знаний решёнными кейсами.
- Управление моделями, prompt-ами, RAG и confidence threshold.
- Мониторинг основный метрик.

## Роли

| Роль | Что делает |
| --- | --- |
| Пользователь | Создаёт обращения, отправляет текст и файлы, получает ответы GigaChat или оператора, закрывает диалог и оставляет оценку ответа. |
| Оператор | Получает эскалированные обращения, видит историю, использует AI-шаблон, редактирует и вручную отправляет ответ клиенту. |
| Администратор | Управляет журналом, модерацией, базой знаний, prompt-ами, AI-настройками и метриками. |

## Основные пользовательские flow

### Flow пользователя

Пользователь создаёт новый Dialog -> отправляет вопрос, screenshot или документ ->
backend выполняет screenshot parse и RAG retrieval -> GigaChat оценивает confidence
-> GigaChat формирует streaming-ответ через SSE -> пользователь продолжает диалог
или закрывает обращение -> пользователь оставляет `helpful`, `ai_error` или не
оставляет оценку (`unrated`).

При явной просьбе об операторе происходит мгновенная эскалация. Первый и второй
low-confidence всё ещё приводят к AI-ответу; третий подряд low-confidence переводит
тот же Dialog в `operator_support`.

### Flow оператора

Эскалация Dialog -> обращение появляется в очереди -> оператор атомарно берёт его
в работу -> видит историю User <-> GigaChat и вложения -> получает AI-шаблон ответа
при необходимости -> редактирует и отправляет ответ вручную -> продолжает общение
с пользователем -> закрывает обращение -> Dialog появляется в журнале
администратора.

#### AI-помощник оператора

История Dialog + attachments + RAG evidence -> `SystemPrompt(operator_gigachat)` ->
GigaChat -> шаблон ответа -> оператор редактирует -> оператор отправляет ответ
вручную.

Backend строит полный упорядоченный снимок сообщений и вложений, затем выбирает
самый свежий фрагмент, помещающийся в context budget. GigaChat никогда не
отправляет операторский шаблон клиенту автоматически.

### Flow администратора

#### Журнал обращений

Закрытый Dialog -> администратор выбирает «Полезные», «AI ошибся» или «Ожидают
оценки» -> открывает полную историю, confidence, модель и moderation state.

Журнал использует server-side pagination и фильтры по дате, способу решения,
наличию вложений и moderation state.

#### Knowledge Candidate

Dialog закрыт -> создаётся один `KnowledgeCandidate` -> администратор редактирует
карточку -> нажимает Approve или Reject -> при Approve карточка проходит Markdown
-> Docling -> BGE-M3 -> Qdrant.

Карточка содержит `Название`, `Проблема` и `Результат`. Candidate создаётся для
каждого закрытого `Dialog`; `UNIQUE(dialog_id)` не позволяет создать дубль.

#### База знаний

Администратор выбирает section -> загружает документ -> Docling разбирает документ
-> создаются structure-aware chunks -> BGE-M3 строит embeddings -> Qdrant сохраняет
индекс -> документ получает статус `indexed` и становится доступен в RAG.

Администратор может:

- создавать, переименовывать и включать/выключать sections;
- загружать PDF, DOCX, HTML и Markdown;
- включать/выключать отдельные документы;
- повторно индексировать failed documents;
- скачивать и удалять документы;
- импортировать Markdown case cards в системный раздел «Журнал обращений».

Список документов выводится по 10 записей. Страница хранится в URL:
`/admin/knowledge?section=<id>&page=<n>`.

#### AI Configuration

Администратор открывает AI Configuration -> изменяет GigaChat model, context ratios,
max output tokens, `rag_top_k`, operator escalation threshold и System Prompts ->
сохраняет настройки без перезапуска приложения.

## Как работает AI

### User AI-turn

```text
USER MESSAGE
    |
    +-- screenshot parse, если есть изображение
    |
    v
RAG retrieval
    |
    v
ONE GenerationContext
    |
    v
CALL #1: structured ConfidenceAssessment
    |
    +-- streak < 3 -> CALL #2: GigaChat answer -> SSE
    |
    +-- streak = 3 -> operator_support без CALL #2
```

Оба GigaChat call используют один и тот же `GenerationContext`. Первый call
использует hardcoded technical confidence prompt. Второй использует редактируемый
`SystemPrompt(type=user_support)` и сразу стримит очищенные chunks пользователю.
Один полный user-turn записывается как один `MetricEvent` с общей latency цепочки:
screenshot parse, RAG, confidence, answer stream, escalation или error.

### Confidence и эскалация

```text
confidence >= threshold
    -> обычный AI flow

первый low-confidence
    -> AI отвечает, streak = 1

второй подряд low-confidence
    -> AI отвечает, streak = 2

третий подряд low-confidence
    -> Dialog -> operator_support

явная просьба пользователя об операторе
    -> мгновенная эскалация
```

Порог по умолчанию составляет 80% и изменяется в AI Settings. При эскалации
оператор подключается к существующему `Dialog`, поэтому пользователю не нужно
повторять проблему.

## Как работает RAG

### Permanent Knowledge Base

```text
PDF / DOCX / HTML / Markdown
        |
        v
Docling
        |
        v
HybridChunker
        |
        v
BGE-M3 dense + sparse embeddings
        |
        v
Qdrant: knowledge_chunks
```

В RAG участвуют только документы со статусом `indexed`, у которых включены и
section, и сам документ. Для поиска используются dense/sparse retrieval и RRF;
результат ограничивается настройкой `rag_top_k`.

### Runtime files != Knowledge Base

Назначение файла определяет pipeline:

```text
Runtime attachment
    -> GigaChat Files API
    -> текущий Dialog

Permanent KB document
    -> Docling
    -> BGE-M3
    -> Qdrant
```

Runtime-вложения не становятся постоянной базой знаний автоматически. Их можно
использовать только в текущем обращении; remote GigaChat file удаляется после
завершения жизненного цикла.

Текущие лимиты runtime upload: до 10 файлов в сообщении, общий размер запроса
менее 80 MB и максимум одно изображение. Изображения поддерживают PNG, JPEG,
TIFF и BMP до 15 MB; документы поддерживают TXT, DOC, DOCX, PDF, EPUB, PPT,
PPTX и XLSX до 40 MB.

Permanent KB принимает PDF, DOCX, HTML и Markdown до 40 MB. Markdown-карточки
для «Журнала обращений» должны быть UTF-8 и не превышать 2 MB.

## Архитектура

```text
React SPA
├── Public landing
├── User panel
├── Operator panel
└── Admin panel
        |
        | REST + SSE
        v
FastAPI modular monolith
├── DialogService
├── GenerationContextService
├── RAGService
├── GigaChatProvider
├── AttachmentService
├── ModerationService
├── KnowledgeBaseService
└── Settings / Monitoring
        |
        +-- PostgreSQL: source of truth
        +-- Qdrant: knowledge_chunks
        +-- Redis: RAG cache and SSE Pub/Sub
        +-- Local/S3 object storage
        +-- GigaChat API
```

Ключевые решения:

- backend остаётся одним модульным FastAPI-монолитом;
- PostgreSQL хранит состояние диалогов, пользователей, сообщений, вложений,
  feedback, candidates, KB metadata, prompt-ов, settings и metrics;
- `BAAI/bge-m3` запускается локально, embedding API GigaChat не используется;
- все GigaChat generation, Vision и Files API вызовы проходят через общий
  `GenerationGate`, а PostgreSQL advisory lock сериализует их между workers;
- Redis используется для versioned RAG cache и доставки SSE-событий между workers;
- PostgreSQL и REST остаются источником истины.

Подробное описание lifecycle, data model, API contract и sequence diagrams:
[`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Стек

| Слой | Технологии |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Routing | React Router v7 |
| Server state | TanStack React Query |
| Backend | Python 3.11, FastAPI, SQLAlchemy |
| LLM | GigaChat |
| LLM integration | LangChain Core, `langchain-gigachat` |
| Embeddings | `BAAI/bge-m3`, FlagEmbedding |
| Vector DB | Qdrant |
| Database | PostgreSQL |
| Cache and events | Redis, Redis Pub/Sub |
| Parsing | Docling |
| Realtime | Server-Sent Events (SSE) |
| Deploy | Docker Compose, Caddy |

## Быстрый запуск

### Требования

- Docker Engine с Docker Compose plugin.
- Сеть во время первого backend build: в образ загружаются BGE-M3, PyTorch и
  Docling artifacts.
- GigaChat credentials для генерации ответов.

Первый build может быть долгим и требовать значительного места на диске. После
сборки backend использует локальные model artifacts и не скачивает модели во время
запросов.

### Development

1. Подготовьте environment:

   ```bash
   cp .env.example .env
   ```

2. Заполните credentials:

   ```dotenv
   GIGACHAT_CREDENTIALS=<Authorization Key из sber.creds>
   GIGACHAT_SCOPE=GIGACHAT_API_PERS
   ```

3. Запустите dev Compose:

   ```bash
   docker compose -f docker-compose.dev.yml up --build -d --wait
   ```

   Или через Makefile:

   ```bash
   make dev-build
   ```

После запуска:

| Сервис | URL |
| --- | --- |
| Frontend | <http://localhost:5173> |
| FastAPI Swagger | <http://localhost:8000/docs> |
| FastAPI ReDoc | <http://localhost:8000/redoc> |
| OpenAPI JSON | <http://localhost:8000/openapi.json> |
| Backend liveness | <http://localhost:8000/health> |
| Qdrant HTTP API | <http://localhost:6333> |

Откройте <http://localhost:5173>. Публичный landing ведёт кнопку «Задать вопрос»
сразу в `/user`; «Вход для команды» открывает переходы в `/operator` и
`/admin/dialogs`.

### Production

Production Compose использует Caddy как единственную внешнюю точку входа. Перед
запуском задайте домен и сильный пароль PostgreSQL:

```bash
export DOMAIN=support.example.com
export POSTGRES_PASSWORD='<long-random-password>'
docker compose -f docker-compose.yml up --build -d --wait
```

Остановить production без удаления данных:

```bash
docker compose -f docker-compose.yml down
```

Caddy получает TLS-сертификат через ACME. PostgreSQL, Qdrant и backend не публикуют
host-порты. Для обновления:

```bash
git pull
docker compose -f docker-compose.yml up --build -d --wait
```

Не удаляйте production directories `PRODUCTION/postgres_data`,
`PRODUCTION/qdrant_data` и `PRODUCTION/backend_storage` без резервной копии.

### Управление dev-стеком

```bash
# Логи backend
docker compose -f docker-compose.dev.yml logs -f backend

# Статус
docker compose -f docker-compose.dev.yml ps

# Остановить контейнеры, сохранив данные
docker compose -f docker-compose.dev.yml down

# Полный reset dev-данных
docker compose -f docker-compose.dev.yml down --volumes --remove-orphans
```

Последняя команда удаляет PostgreSQL, Qdrant и local storage volumes.

## Основные маршруты

| URL | Назначение |
| --- | --- |
| `/` | Public landing |
| `/user` | Панель пользователя |
| `/user/new` | Новый Dialog |
| `/operator` | Очередь оператора |
| `/operator/dialogs/:dialogId` | Dialog оператора |
| `/admin/dialogs` | Журнал обращений |
| `/admin/knowledge` | База знаний |
| `/admin/prompts` | System Prompts |
| `/admin/settings` | AI Settings |
| `/admin/monitoring` | Monitoring |

Маршрут `/admin` перенаправляет в `/admin/dialogs`.

## Основные сущности

```text
Dialog
├── Message
│   └── Attachment
├── DialogFeedback
└── KnowledgeCandidate

KnowledgeSection
└── KnowledgeDocument
    └── Chunk

SystemPrompt
SystemSetting
MetricEvent
```

## Realtime

```text
REST
    -> mutations and persisted state

SSE
    -> answer streaming and state events

Redis Pub/Sub
    -> delivery between backend workers

PostgreSQL
    -> source of truth
```

Основные SSE endpoints:

```text
GET /api/dialogs/:dialogId/events
GET /api/operator/events
GET /api/operator/dialogs/:dialogId/events
```

User stream передаёт confidence state, answer tokens, завершённый ответ,
подключение оператора и ошибки. Operator streams передают события очереди,
новые сообщения, закрытие обращения и отзыв доступа. Redis Pub/Sub не хранит
event log: replay по `Last-Event-ID` не реализован.

## Monitoring

Административная панель агрегирует по периодам `today`, `7 days`, `30 days` и
`all time`:

- количество user turns;
- долю обращений, решённых AI;
- долю эскалаций;
- среднее время ответа;
- helpful feedback;
- failed requests на backend API.

Один `user message` с цепочкой screenshot/RAG/confidence/answer или escalation
считается одним `MetricEvent(event_type="user_turn")`. В текущем API есть average
latency, но p50/p95 и отдельная UI-карточка `failed_requests` пока не реализованы.

## Ограничения MVP

- Authentication и production RBAC отсутствуют. `X-Molvest-Role` используется только
  как demo actor context и не является security boundary.
- Реальные Bitrix24 и Redmine adapters/webhooks не реализованы.
- Redis Pub/Sub не поддерживает replay, transactional outbox отсутствует.
- Нет отдельной durable task queue Celery/RQ; persisted recovery выполняется самим
  backend.
- Один поток GigaChat generation сериализуется через `GenerationGate`.
- `/health` является liveness endpoint и не проверяет все зависимости и readiness.
- PostgreSQL schema создаётся через `Base.metadata.create_all`; Alembic и migration
  scripts отсутствуют.
- Нет автоматического backend/frontend test runner и coverage configuration.
- Monitoring не считает p50/p95, не показывает raw logs и alerting.
- Реальная документация 1С не импортируется автоматически при startup.
- Kubernetes и микросервисная архитектура не входят в MVP.

## Roadmap

- Bitrix24 Open Lines adapter.
- Redmine HelpDesk adapter.
- Production authentication и RBAC.
- Transactional outbox и event replay.
- Durable background queue.
- Расширенный monitoring и alerting.
- Automated RAG evaluation и golden datasets.
- Reranker при подтверждённой необходимости.
- Массовый импорт реальной базы знаний заказчика.

## Проверки проекта

Backend требует Python `>=3.11,<3.12` и заранее созданный `backend/.venv`:

```bash
make check-backend
```

Команда запускает Ruff lint, Ruff format check и Mypy.

Frontend:

```bash
make check-frontend
npm --prefix frontend run build
```

`make check-frontend` запускает ESLint и TypeScript typecheck. Отдельного unit-test
runner в текущем репозитории нет.

## Структура репозитория

```text
.
├── backend/                 # FastAPI, services, providers, models
├── frontend/                # React SPA: user, operator, admin
├── docker-compose.yml       # production Compose + Caddy
├── docker-compose.dev.yml   # development Compose + hot reload
├── ARCHITECTURE.md          # полный engineering contract
├── Makefile                 # запуск и проверки
└── README.md                # быстрый вход в проект
```

Внутри `backend/` основные каталоги: `api`, `contracts`, `core`, `models`,
`providers`, `services`. Внутри `frontend/src/`: `app`, `api`, `features` и
`shared`. Актуальный runtime frontend находится в `frontend/src`; файл
`molvest_support_redesign.html` является отдельным static design prototype.

## Правила разработки

- PostgreSQL остаётся source of truth.
- React Query используется для frontend server state.
- REST используется для команд и мутаций, SSE для streaming и realtime.
- Интеграция с GigaChat проходит через `GigaChatProvider`, используя LangChain
  first подход.
- Не добавлять Redux/Zustand, микросервисы или agent orchestration без измеримой
  необходимости.
- Подробные архитектурные решения и актуальные API-контракты фиксируются в
  [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Документация

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — полная архитектура, lifecycle, data model,
  API и sequence diagrams.
- `/docs` — Swagger UI в development.
- `/redoc` — ReDoc в development.
- `/openapi.json` — OpenAPI schema в development.

## Проект

Проект подготовлен для хакатона по автоматизации технической поддержки АО
«Молвест» с использованием Sber GigaChat.

Контакт по предметной области: **Виктория Владимировна Донцова**, ведущий
специалист (аналитик), АО «Молвест».
