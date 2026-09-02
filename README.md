# Molvest 1C Support

## Development

The development stack uses separate volumes and runs both application processes
with hot reload:

```bash
cp .env.example .env
make dev-build
```

After the first image build, use `make dev`. Backend changes under `backend/app`
restart Uvicorn, while frontend changes under `frontend/src` are applied through
Vite HMR.

- Frontend: <http://localhost:5173>
- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Qdrant dashboard: <http://localhost:6333/dashboard>

Stop the stack with `make dev-down`. Dependency changes in `pyproject.toml` or
`package-lock.json` require `make dev-build` again.

## Production

The production stack runs Alembic migrations before starting Uvicorn and serves
the compiled SPA through Nginx:

```bash
cp .env.production.example .env
# Set JWT_SECRET, GIGACHAT_CREDENTIALS and deployment-specific values.
make prod
```

- Application: <http://localhost>
- Swagger UI: <http://localhost/docs>
- ReDoc: <http://localhost/redoc>

Production cookies are secure, so a real deployment must expose the frontend
through HTTPS. PostgreSQL, Qdrant and the backend are not published directly.
Stop the stack with `make prod-down`.

## Code Checks

Backend checks use the repository-local virtual environment:

```bash
bash backend/check.sh
# or from the repository root:
make check-backend
make check-frontend
```

The only retained test utility is the RAG retrieval check. It runs in the
backend development image against the development PostgreSQL and Qdrant:

```bash
make rag-check
```

FastAPI OpenAPI is the source of truth for the HTTP API; no separate API contract
is maintained outside Swagger UI and ReDoc.
