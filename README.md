# Molvest Support

AI-сервис технической поддержки пользователей 1С: собственный web-чат,
гибридный RAG по базе знаний, анализ скриншотов через GigaChat Vision и передача
сложных обращений оператору.

Проект реализован как демонстрационный MVP для АО «Молвест». В репозитории есть
полный web-flow с тремя role-зонами, backend API, ingestion базы знаний,
модерация закрытых кейсов и production Compose-стек с Caddy. Интеграции Bitrix24 и
Redmine, production identity provider и горизонтальное масштабирование остаются
roadmap.

> 🎯 **Задача хакатона:** разработать интеллектуального AI-агента для автоматизации
> технической поддержки пользователей 1С — с централизованной базой знаний,
> анализом скриншотов, эскалацией сложных обращений и измеримым эффектом для
> команды поддержки.

## Контекст и цели

**Заказчик:** АО «Молвест»

Проект нацелен на четыре бизнес-результата:

| Цель | Ориентир |
| --- | --- |
| Снизить нагрузку на техподдержку | на 30–40% меньше обращений к операторам |
| Сократить ожидание ответа | менее 5 секунд до генерации ответа / первого streaming token |
| Повысить качество ответов | единая актуальная база знаний и единый AI-подход |
| Обеспечить доступность | круглосуточная автоматическая первая линия поддержки |

Текущий репозиторий закрывает демонстрационный web-срез задачи. Bitrix24 и Redmine
описаны как целевые каналы интеграции, но adapters к ним пока не реализованы.

## Возможности

### Пользователь

- Создание и ведение нескольких обращений.
- Ответы AI по истории диалога и индексированной базе знаний.
- Streaming ответа через SSE.
- Прикрепление до 10 файлов в сообщении, включая максимум один скриншот.
- Анализ PNG/JPEG/TIFF/BMP через GigaChat Vision.
- Передача сложного обращения оператору по явной просьбе или после трёх
  последовательных низких оценок confidence.
- Закрытие решённого обращения и итоговая оценка `helpful` или `ai_error`.

### Оператор

- Очередь неназначенных и собственных обращений.
- Атомарный claim тикета с защитой от одновременного назначения.
- Полная история диалога и вложения.
- Ручная отправка ответа.
- Генерация редактируемого шаблона ответа через отдельный GigaChat-вызов.
- Закрытие обращения и realtime-события о смене доступа.

### Администратор

- Журнал закрытых обращений с фильтрами `helpful`, `ai_error`, `unrated`.
- Просмотр диалога, confidence, модели, prompt snapshot и moderation state.
- Модерация `KnowledgeCandidate`: редактирование, генерация карточки, approve/reject.
- Разделы базы знаний: создание, переименование, включение/выключение, удаление.
- Документы базы знаний: upload, download, enable/disable, reindex и delete.
- Редактирование трёх системных prompt без перезапуска.
- Изменение AI/RAG settings без перезапуска.
- Агрегированный monitoring по периодам от today до all time.

## Сценарии агента и соответствие задаче

### 1. Вопрос–ответ 💬

Пользователь задаёт вопрос в web-чате. Backend собирает историю обращения,
релевантные фрагменты БЗ и вложения, после чего GigaChat формирует понятный
пошаговый ответ. При явной просьбе о специалисте или трёх последовательных низких
оценках confidence тот же тикет передаётся оператору.

В постановке задачи целевыми каналами указаны Bitrix24 и Redmine HelpDesk. В текущем
MVP этот сценарий демонстрируется через собственный frontend; channel adapters и
webhooks для внешних систем остаются следующим этапом.

### 2. Автоматическое подключение к существующему чату 🔌

Архитектура оставляет backend независимым от UI и предусматривает будущий режим,
в котором агент читает сообщения внешнего чата и либо предлагает оператору черновик,
либо отвечает автоматически по настройке. Реализация Bitrix24 Open Lines и Redmine
HelpDesk не входит в текущий код MVP.

### 3. Анализ изображений 🖼️

Пользователь может приложить screenshot 1С в любом диалоге. Поддерживаются
PNG/JPEG/TIFF/BMP; GigaChat Vision извлекает текст и визуальные признаки, после чего
результат участвует в поиске по БЗ и генерации рекомендаций. Backend также принимает
текстовые и офисные runtime-документы в пределах установленных лимитов.

### 4. Управление базой знаний 📚

Администратор управляет секциями и документами, запускает reindex, включает или
выключает источники и публикует успешно разобранные кейсы из журнала обращений.
Новые permanent-документы проходят Docling → BGE-M3 → Qdrant и становятся доступны
агенту только после успешной индексации.

## Источники данных

Система рассчитана на следующие источники из постановки задачи:

- **Внутренняя база знаний техподдержки:** инструкции, регламенты и памятки в PDF,
  DOCX, HTML и Markdown.
- **Документация 1С:** официальные материалы по платформе и конфигурациям,
  руководства пользователя и администратора. Загружаются администратором через KB
  interface; автоматического импорта внешнего массива при startup нет.
- **Журнал обращений:** закрытые диалоги, feedback и approved knowledge candidates,
  которые после модерации публикуются в защищённую секцию «Журнал обращений».
- **Пользовательские изображения и файлы:** runtime-контекст конкретного обращения,
  который не становится постоянной БЗ автоматически.

## Архитектура

```text
React 18 + TypeScript + Vite SPA
    ├── User panel
    ├── Operator panel
    └── Admin panel
             │ REST + SSE
             ▼
FastAPI modular monolith
    ├── DialogService
    ├── GenerationContext / AttachmentService
    ├── RAGService
    ├── KnowledgeBaseService
    ├── ModerationService
    ├── Settings / Monitoring services
    └── GigaChatProvider
             │
    ┌────────┼─────────┬──────────────┐
    ▼        ▼         ▼              ▼
 PostgreSQL Qdrant  Local/S3       GigaChat
```

Ключевые решения:

- Backend — один модульный FastAPI-монолит, не набор микросервисов.
- PostgreSQL хранит пользователей, диалоги, сообщения, вложения, feedback,
  candidates, KB metadata, prompts, settings и metrics.
- Qdrant хранит одну hybrid-коллекцию `knowledge_chunks` с dense+sparse-векторами.
- `BAAI/bge-m3` работает локально; embedding API GigaChat не используется.
- GigaChat применяется для confidence, финального ответа, Vision и operator
  template. Интеграция идёт через `langchain-gigachat` и LangChain Core.
- Документы разбираются Docling, чанки индексируются в BGE-M3 и Qdrant.
- Все GigaChat generation, Vision и Files API операции проходят через
  process-local `GenerationGate`, что соответствует ограничению одного потока
  Freemium. Пользовательский AI-turn дополнительно защищён PostgreSQL advisory
  lock и проверкой `pending/processing` trigger-сообщений.
- Текущий web-канал использует REST/SSE. Bitrix24/Redmine adapters пока не
  реализованы.

Полный архитектурный контракт, data model, API tables и sequence diagrams находятся
в [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Требования

- Docker Engine с Docker Compose plugin.
- Доступ к сети во время первого backend build: образ скачивает BGE-M3, PyTorch и
  Docling/EasyOCR artifacts.
- `package-lock.json` для frontend build уже включён в репозиторий.
- GigaChat credentials для AI-ответов. Без них можно поднять инфраструктуру и
  просматривать часть UI, но генерация не будет работать.

Первый build backend может быть долгим и требует заметного места на диске: в образ
встраиваются модель embeddings и Docling artifacts. Во время runtime backend
работает в offline-режиме Hugging Face и не скачивает модели из сети.

## Быстрый запуск для разработки

### 1. Подготовить окружение

```bash
cp .env.example .env
```

Для полноценного AI-flow укажите в `.env`:

```dotenv
GIGACHAT_CREDENTIALS=<Authorization Key из sber.creds>
```

Единый `.env.example` содержит комментарии ко всем переменным и используется как
для dev, так и для production. Dev Compose сам переопределяет внутренние адреса
сервисов и `CORS_ORIGINS` для localhost.

### 2. Запустить dev Compose

```bash
docker compose -f docker-compose.dev.yml up --build -d --wait
```

После запуска:

| Назначение | URL |
| --- | --- |
| Frontend | <http://localhost:5173> |
| FastAPI Swagger | <http://localhost:8000/docs> |
| FastAPI ReDoc | <http://localhost:8000/redoc> |
| OpenAPI JSON | <http://localhost:8000/openapi.json> |
| Backend liveness | <http://localhost:8000/health> |
| Qdrant HTTP API | <http://localhost:6333> |

На стартовой странице выберите demo-роль: пользователь, оператор или
администратор. Demo login включён только в development Compose.

### Управление dev-стеком

```bash
# Логи
docker compose -f docker-compose.dev.yml logs -f backend

# Статус
docker compose -f docker-compose.dev.yml ps

# Остановить контейнеры, сохранив данные
docker compose -f docker-compose.dev.yml down

# Удалить PostgreSQL, Qdrant и local storage
docker compose -f docker-compose.dev.yml down --volumes --remove-orphans
```

В dev Compose опубликованы только на loopback-интерфейсе порты PostgreSQL `5432`,
Qdrant `6333/6334`, backend `8000` и frontend `5173`. Их можно изменить через
`.env`; из внешней сети эти сервисы не доступны.

## Как пользоваться MVP

1. Войдите demo-пользователем и создайте обращение.
2. Отправьте вопрос и при необходимости приложите screenshot или документ.
3. Backend сохранит сообщение, соберёт контекст, выполнит hybrid retrieval,
   confidence assessment и начнёт streaming ответа.
4. При явной просьбе об операторе или третьем подряд низком confidence диалог
   перейдёт в `operator_support`.
5. Оператор заберёт тикет, при необходимости сгенерирует шаблон, отредактирует и
   отправит ответ.
6. После закрытия диалога пользователь оставит feedback. Backend создаст
   `KnowledgeCandidate`, который администратор может проверить и опубликовать в
   секции «Журнал обращений».

## Ожидаемый результат и текущий статус ✅

| Ожидаемый результат постановки | Статус в репозитории |
| --- | --- |
| Работающий AI-агент | Реализован web-MVP с REST/SSE, RAG, GigaChat и operator handoff |
| Интеграция с Bitrix24 / Redmine | Roadmap: backend channel adapters ещё не реализованы |
| Актуальная база знаний | Реализованы секции, upload, Docling ingestion, Qdrant retrieval, reindex и delete |
| Анализ скриншотов | Реализован GigaChat Vision flow для PNG/JPEG/TIFF/BMP |
| Панель администратора | Реализованы журнал, moderation, KB, prompts, settings и aggregate monitoring |
| Просмотр логов | Отдельного log viewer в UI нет; доступны container/application logs |
| Настройка confidence и эскалации | Реализована через admin settings без restart |
| Метрики эффективности | Реализованы AI-resolved rate, escalation rate, helpful rate и average latency |
| Эксплуатационная документация | `README.md`, `ARCHITECTURE.md`, Swagger/ReDoc и Compose runbooks |

Целевые показатели 30–40% и менее 5 секунд являются KPI постановки задачи. В
репозитории есть сбор aggregate metrics и golden RAG evaluator, но финальное
подтверждение бизнес-KPI требует данных реальной эксплуатации и нагрузочных замеров.

## База знаний

### Permanent documents

Администратор загружает документы в выбранную секцию. Поддерживаются:

- PDF;
- DOCX;
- HTML/HTM;
- Markdown/MD.

Максимальный размер permanent document — 40 MB. Раздел «Журнал обращений» нельзя
заполнять прямой загрузкой: он пополняется только approved candidates.

Pipeline индексации:

```text
upload
  → object storage
  → Docling parser
  → HybridChunker, до 800 токенов
  → BGE-M3 dense + sparse embeddings
  → Qdrant collection knowledge_chunks
```

В RAG участвуют только документы со статусом `indexed`, у которых включены и
секция, и сам документ. При удалении документа backend удаляет его точки из
Qdrant, object-storage object, SQL-запись и связанные chunks; approved candidates,
ссылающиеся на документ, переводятся в `rejected` и отвязываются. Поставленная до
удаления ingestion-задача не восстанавливает документ.

### Runtime attachments

Для сообщения можно отправить до 10 файлов, общий размер запроса должен быть менее
80 MB, максимум один файл может быть изображением:

- images: PNG/JPEG/TIFF/BMP, до 15 MB;
- documents: TXT/DOC/DOCX/PDF/EPUB/PPT/PPTX/XLSX, до 40 MB.

Файлы проходят backend validation по расширению, MIME и базовым magic bytes.
Изображения анализируются GigaChat Vision. Runtime originals хранятся в local или
S3-compatible storage до закрытия/hard delete диалога; remote GigaChat file IDs
удаляются при cleanup.

## Production deployment

Production Compose предназначен для server deployment с единственной внешней
точкой входа:

- Caddy публикует TCP `80`, TCP `443` и UDP `443` для HTTP/3.
- Caddy автоматически получает и обновляет TLS-сертификат через ACME.
- PostgreSQL, Qdrant и backend не имеют host-портов.
- Caddy сам собирает и раздаёт статический React bundle.
- Caddy проксирует `/api/` напрямую во внутренний backend.
- Swagger/ReDoc/OpenAPI доступны только в development; в production API-документация
  отключена.

### Подготовка сервера

1. Создайте DNS `A`/`AAAA` запись домена на IP сервера.
2. Разрешите в firewall входящие TCP `80`, TCP `443` и UDP `443`.
3. Установите Docker Engine и Compose plugin.
4. Клонируйте репозиторий на сервер.
5. Подготовьте `.env` из единого шаблона:

```bash
cp .env.example .env
```

Обязательно замените минимум:

```dotenv
DOMAIN=support.example.com
POSTGRES_PASSWORD=<long-random-password>
GIGACHAT_CREDENTIALS=<Authorization Key>
```

`DOMAIN` указывается без `https://` и без path. Не коммитьте `.env` и credentials.

### Запуск

```bash
docker compose -f docker-compose.yml up --build -d --wait
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml logs -f caddy
```

Остановить контейнеры без удаления данных:

```bash
docker compose -f docker-compose.yml down
```

Сохраняйте volumes `caddy_data` и `caddy_config`: в них находится состояние
сертификатов и Caddy. Для обычного обновления используйте:

```bash
git pull
docker compose -f docker-compose.yml up --build -d --wait
```

### Важное ограничение production authentication

Production Compose не включает login/auth provisioning и задаёт `SEED_ON_STARTUP=false`.
Это означает, что при чистом production volume не создаются demo users, системные
sections, prompts и settings.
В текущем коде единственный login — demo endpoint; production identity provider,
регистрация пользователей, SSO и отзыв уже выданных JWT ещё не реализованы. Поэтому
production Compose уже готов как TLS/private-network deployment baseline, но
end-user authentication и первичное provisioning для реального публичного запуска
требуют отдельной интеграции IdP/SSO.

Не включайте demo login в публичной среде как замену identity provider.

## Конфигурация

Все переменные находятся в корневом `.env.example` без комментариев, чтобы файл можно
было напрямую копировать в `.env`. Подробное описание настроек:

| Переменная | Допустимые значения и назначение |
| --- | --- |
| `DOMAIN` | DNS-имя production-сервера без `https://` и path, например `support.example.com`. Caddy использует его для TLS и маршрутизации. В dev не используется. |
| `POSTGRES_PASSWORD` | В production обязательна сильная URL-safe строка. Не используйте `@`, `:`, `/`, `#`, `%`, потому что значение входит в PostgreSQL URL. В dev пустое значение заменяется локальным fallback `molvest`. |
| `STORAGE_BACKEND` | `local` или `s3`. `local` использует named Docker volume, `s3` — внешний S3-compatible storage. |
| `S3_ENDPOINT_URL` | URL S3 endpoint, например `https://s3.example.com`; для AWS можно оставить пустым. Используется только при `STORAGE_BACKEND=s3`. |
| `S3_REGION` | Непустой регион S3, например `us-east-1`. |
| `S3_BUCKET` | Непустое имя bucket, например `molvest`. |
| `S3_ACCESS_KEY_ID` | S3 access key; обязателен при `STORAGE_BACKEND=s3`. |
| `S3_SECRET_ACCESS_KEY` | S3 secret key; обязателен при `STORAGE_BACKEND=s3`. Не коммитьте это значение. |
| `S3_USE_SSL` | `true` или `false`; использовать HTTPS для S3 endpoint. Для production рекомендуется `true`. |
| `QDRANT_API_KEY` | Пусто для локального Qdrant либо API key защищённого внешнего Qdrant. |
| `GIGACHAT_CREDENTIALS` | Authorization Key из `sber.creds`; пустое значение отключает GigaChat generation. Не коммитьте credentials. |
| `GIGACHAT_SCOPE` | Scope, выданный для ключа, обычно `GIGACHAT_API_PERS`. |

По умолчанию используется local object storage в Docker volume. MinIO в Compose не
входит; для S3 нужно предоставить внешний endpoint и credentials. Production Compose
переопределяет внутренние hostnames, порты, CORS, seed, embedding device и тайминги.
PostgreSQL user/database (`molvest`), Qdrant URL и остальные внутренние service
defaults находятся в Compose и не требуют `.env`.

`ENVIRONMENT` не является пользовательской переменной: dev Compose передаёт
`development`, production Compose передаёт `production`. Backend использует режим,
чтобы включить dev Swagger/demo defaults и отключить demo login в production.

## Проверки и тесты

### Static checks

Backend требует Python `>=3.11,<3.12` и заранее созданный `backend/.venv`:

```bash
make check-backend
```

Команда запускает Ruff lint, Ruff format check и Mypy. Unit-тесты в неё не входят.

Frontend:

```bash
make check-frontend
npm --prefix frontend run build
```

Отдельный unit-test runner и coverage configuration в текущем репозитории отсутствуют.

## Операционные ограничения

- `/health` — только liveness endpoint, он не проверяет PostgreSQL, Qdrant, GigaChat,
  storage и готовность моделей.
- Схема создаётся через `Base.metadata.create_all`; Alembic/migrations отсутствуют.
  Изменения модели на persistent database могут потребовать ручной миграции или
  пересоздания volume.
- Background tasks, ingestion recovery, GenerationGate и EventBroker работают
  внутри процесса. Нет Redis/Celery, durable queue, cross-worker SSE replay или
  внешнего pub/sub; полноценные replicas не поддерживаются.
- SSE использует native EventSource, heartbeat и polling fallback, но не реализует
  replay по `Last-Event-ID`.
- Monitoring отдаёт aggregate metrics, average latency и failed request count; p50/p95,
  raw logs, alerting и time-series charts не реализованы в UI.
- RAG source snapshots сохраняются внутренне, но текущий `MessageDto` и frontend не
  показывают список источников.
- Размер runtime-файлов не полностью отражается в локальном context budget; отдельного
  автоматического fallback при переполнении GigaChat Files API нет.
- Компенсация при частично успешной загрузке remote files и согласованность
  PostgreSQL/Qdrant/storage не являются distributed transaction.
- Hard delete закрытого диалога пока не проверяет `DialogFeedback.verdict == ai_error`;
  backend policy шире текущей moderation-идеи.
- Нет реальной интеграции Bitrix24/Redmine и нет production identity provider.

## Структура репозитория

```text
backend/
  app/
    api/          FastAPI REST + SSE routes
    contracts/    Pydantic DTOs
    core/         config, auth, database, locks
    models/       SQLAlchemy entities
    providers/    GigaChat, embeddings, Docling, Qdrant, storage
    services/     dialogs, RAG, KB, moderation, settings, tasks
  Dockerfile
frontend/
  src/
    app/          router, layouts, providers, guards
    api/          REST client, DTOs, query keys
    features/     auth, user, operator and admin screens
  shared/       chat, hooks and UI primitives
  Dockerfile
Dockerfile.caddy   production static frontend + Caddy image
Caddyfile          production TLS, SPA and API proxy
docker-compose.yml
.env.example
ARCHITECTURE.md
Makefile
```

`molvest_support_redesign.html` — самостоятельный статический design prototype и не
является runtime-frontend. Источник актуального интерфейса — `frontend/src`.

## Контакт по предметной области ☎️

**Виктория Владимировна Донцова**<br>
Ведущий специалист (аналитик), АО «Молвест»

- Телефон: `+7 (473) 206-68-00`, доб. `2833`
- E-mail: <v.dontsova@molvest.ru>

## Дополнительная документация

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — подробный архитектурный контракт,
  lifecycle, data model, API и sequence diagrams.
- Swagger UI — `/docs` в development.
- ReDoc — `/redoc` в development.
- OpenAPI JSON — `/openapi.json` в development.
