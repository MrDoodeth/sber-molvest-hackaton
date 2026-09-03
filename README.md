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

## Проверки

```bash
make check-backend
make check-frontend
```

Архитектурные решения и текущий MVP-контракт описаны в
[`ARCHITECTURE.md`](ARCHITECTURE.md).
