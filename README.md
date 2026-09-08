# Molvest Support

AI-сервис технической поддержки пользователей 1С: чат, RAG по базе знаний,
анализ вложений и передача сложных обращений оператору.

## Быстрый запуск

Требуется Docker с поддержкой `docker compose`.

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build -d --wait
```

После запуска:

- приложение: http://localhost:5173
- API и Swagger: http://localhost:8000/docs
- healthcheck: http://localhost:8000/health

На стартовом экране выберите одну из demo-ролей: пользователь, оператор или
администратор. Для ответов GigaChat укажите `GIGACHAT_CREDENTIALS` в `.env`.

Первый build может быть долгим: backend загружает в Docker image BGE-M3 и
модели Docling. Во время работы backend использует эти локальные artifacts и не
скачивает модели из сети.

## Управление

Посмотреть логи:

```bash
docker compose -f docker-compose.dev.yml logs -f backend
```

Остановить сервисы:

```bash
docker compose -f docker-compose.dev.yml down
```

Полностью сбросить данные PostgreSQL, Qdrant и локальное хранилище:

```bash
docker compose -f docker-compose.dev.yml down --volumes --remove-orphans
```

## Production Deployment

`docker-compose.yml` publishes only Caddy on TCP `80` and `443` (and UDP `443` for
HTTP/3). PostgreSQL, Qdrant, backend and frontend nginx have no published host ports;
the browser reaches the SPA and same-origin `/api` only through Caddy.

Before starting the stack, point the DNS `A`/`AAAA` record for the selected domain to
the server and allow inbound TCP `80`, TCP `443` and UDP `443` in the firewall. Caddy
uses port `80` for ACME validation and obtains and renews the TLS certificate itself.

```bash
cp .env.example .env
# Set DOMAIN, CADDY_EMAIL, POSTGRES_PASSWORD and JWT_SECRET in .env.
docker compose -f docker-compose.yml up --build -d --wait
```

The production Compose disables demo authentication and seed data, independently of
the common `.env` values. Keep the named `caddy_data` volume when updating the stack
so certificate state survives.

```bash
docker compose -f docker-compose.yml logs -f caddy
docker compose -f docker-compose.yml down
```

## Проверки

```bash
make check-backend
make check-frontend
```

Архитектурные решения и текущий MVP-контракт описаны в
[`ARCHITECTURE.md`](ARCHITECTURE.md).
