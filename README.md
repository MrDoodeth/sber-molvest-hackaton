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

| Роль          | Что делает                                                                                                                       |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Пользователь  | Создаёт обращения, отправляет текст и файлы, получает ответы GigaChat или оператора, закрывает диалог и оставляет оценку ответа. |
| Оператор      | Получает эскалированные обращения, видит историю, использует AI-шаблон, редактирует и вручную отправляет ответ клиенту.          |
| Администратор | Управляет журналом, модерацией, базой знаний, prompt-ами, AI-настройками и метриками.                                            |

## Основные пользовательские сценарии

### Сценарий пользователя

Пользователь создаёт новое обращение -> отправляет вопрос, снимок экрана или документ
-> серверная часть анализирует снимок экрана и выполняет поиск по базе знаний ->
GigaChat оценивает уверенность ответа -> GigaChat формирует потоковый ответ через SSE
-> пользователь продолжает диалог
или закрывает обращение -> пользователь оставляет `helpful`, `ai_error` или не
оставляет оценку (`unrated`).

При явной просьбе об операторе происходит мгновенная эскалация. Первый и второй
случаи низкой уверенности всё ещё приводят к ответу AI; третий подряд случай низкой
уверенности переводит то же обращение в режим `operator_support`.

### Сценарий оператора

Эскалация обращения -> обращение появляется в очереди -> оператор берёт его
в работу -> видит историю общения с пользователем и GigaChat, а также вложения ->
получает при необходимости шаблон ответа от AI на основе всего чата -> редактирует и отправляет ответ
вручную -> продолжает общение с пользователем -> закрывает обращение -> обращение
появляется в журнале
администратора.

### Сценарий администратора

#### Журнал обращений

Закрытое обращение -> администратор выбирает «Полезные», «AI ошибся» или «Ожидают
оценки» -> открывает полную историю, уверенность ответа, модель и состояние
модерации.

#### Кандидат в базу знаний

Обращение закрыто -> создаётся один `KnowledgeCandidate` -> администратор редактирует
карточку -> одобряет или отклоняет её -> при одобрении карточка проходит Markdown
-> Docling -> BGE-M3 -> Qdrant.

Карточка содержит `Название`, `Проблема` и `Результат`.

#### База знаний

Администратор выбирает раздел -> загружает документ -> Docling разбирает документ ->
создаются структурированные фрагменты -> BGE-M3 строит векторные представления ->
Qdrant сохраняет индекс -> документ получает статус `indexed` и становится доступен
для поиска.

Администратор может:

- создавать, переименовывать и включать/выключать разделы;
- загружать PDF, DOCX, HTML и Markdown;
- включать/выключать отдельные документы;
- повторно индексировать документы с ошибкой;
- скачивать и удалять документы;
- импортировать Markdown-карточки кейсов в системный раздел «Журнал обращений».

#### Настройки AI

Администратор открывает настройки AI -> изменяет модель GigaChat, доли контекста,
максимальное число выходных токенов, `rag_top_k`, порог передачи оператору и
системные промпты -> сохраняет настройки без перезапуска приложения.

## Как работает AI

### Обработка вопроса

Сообщение пользователя -> анализ снимка экрана, если он приложен -> поиск по базе
знаний -> построение единого `GenerationContext` -> первый вызов GigaChat с
`ConfidenceAssessment` -> проверка уверенности -> второй вызов GigaChat с
`SystemPrompt(type=user_support)` -> передача ответа пользователю потоком через SSE.

Оба вызова GigaChat используют один и тот же `GenerationContext`. Первый использует
встроенную техническую инструкцию для оценки уверенности. Второй формирует ответ
и сразу передаёт его очищенные фрагменты пользователю. Полный пользовательский
оборот записывается как один `MetricEvent` с общей задержкой: анализ снимка экрана,
поиск по базе знаний, оценка уверенности, ответ, передача оператору или ошибка.

### Уверенность и передача оператору

Уверенность не ниже порога -> обычный ответ AI.

Первая низкая оценка -> AI отвечает -> счётчик низких оценок равен 1.

Вторая подряд низкая оценка -> AI отвечает -> счётчик низких оценок равен 2.

Третья подряд низкая оценка -> обращение переводится в `operator_support` без
дополнительного вызова GigaChat.

Явная просьба пользователя об операторе -> немедленная передача обращения
оператору. Порог по умолчанию составляет 80% и изменяется в настройках AI.
Оператор подключается к существующему обращению, поэтому пользователю не нужно
повторять проблему.

## Как работает RAG

### Постоянная база знаний

Документ PDF, DOCX, HTML или Markdown -> Docling -> `HybridChunker` -> плотные и
разреженные векторные представления BGE-M3 -> коллекция `knowledge_chunks` в Qdrant.

В поиске участвуют только документы со статусом `indexed`, у которых включены и
раздел, и сам документ. Система выполняет гибридный поиск, объединяет результаты
с помощью RRF и ограничивает выдачу настройкой `rag_top_k`.

### Временные вложения и постоянная база знаний

Вложение только для текущего обращения -> GigaChat Files API -> текущий диалог.

Документ, который администратор добавляет в базу знаний -> Docling -> BGE-M3 ->
Qdrant.

Временное вложение не становится постоянной базой знаний автоматически. Оно
используется только в текущем обращении, а удалённый файл GigaChat удаляется после
завершения его жизненного цикла.

Текущие ограничения вложений в сообщении: до 10 файлов, общий размер запроса менее
80 MB и не более одного изображения. Изображения поддерживают PNG, JPEG, TIFF и
BMP до 15 MB; документы поддерживают TXT, DOC, DOCX, PDF, EPUB, PPT, PPTX и XLSX
до 40 MB.

Постоянная база знаний принимает PDF, DOCX, HTML и Markdown до 40 MB.
Markdown-карточки для «Журнала обращений» должны быть в UTF-8 и не превышать 2 MB.

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

| Слой             | Технологии                               |
| ---------------- | ---------------------------------------- |
| Frontend         | React 18, TypeScript, Vite, Tailwind CSS |
| Routing          | React Router v7                          |
| Server state     | TanStack React Query                     |
| Backend          | Python 3.11, FastAPI, SQLAlchemy         |
| LLM              | GigaChat                                 |
| LLM integration  | LangChain Core, `langchain-gigachat`     |
| Embeddings       | `BAAI/bge-m3`, FlagEmbedding             |
| Vector DB        | Qdrant                                   |
| Database         | PostgreSQL                               |
| Cache and events | Redis, Redis Pub/Sub                     |
| Parsing          | Docling                                  |
| Realtime         | Server-Sent Events (SSE)                 |
| Deploy           | Docker Compose, Caddy                    |

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

| Сервис           | URL                                  |
| ---------------- | ------------------------------------ |
| Frontend         | <http://localhost:5173>              |
| FastAPI Swagger  | <http://localhost:8000/docs>         |
| FastAPI ReDoc    | <http://localhost:8000/redoc>        |
| OpenAPI JSON     | <http://localhost:8000/openapi.json> |
| Backend liveness | <http://localhost:8000/health>       |
| Qdrant HTTP API  | <http://localhost:6333>              |

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

| URL                           | Назначение          |
| ----------------------------- | ------------------- |
| `/`                           | Public landing      |
| `/user`                       | Панель пользователя |
| `/user/new`                   | Новый Dialog        |
| `/operator`                   | Очередь оператора   |
| `/operator/dialogs/:dialogId` | Dialog оператора    |
| `/admin/dialogs`              | Журнал обращений    |
| `/admin/knowledge`            | База знаний         |
| `/admin/prompts`              | System Prompts      |
| `/admin/settings`             | AI Settings         |
| `/admin/monitoring`           | Monitoring          |

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
