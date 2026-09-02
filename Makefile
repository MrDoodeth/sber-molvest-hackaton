.PHONY: dev dev-build dev-down prod prod-down check-backend check-frontend rag-check

dev:
	docker compose -f docker-compose.dev.yml up

dev-build:
	docker compose -f docker-compose.dev.yml up --build

dev-down:
	docker compose -f docker-compose.dev.yml down

prod:
	docker compose -f docker-compose.yml up --build -d

prod-down:
	docker compose -f docker-compose.yml down

check-backend:
	bash backend/check.sh

check-frontend:
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck

rag-check:
	docker compose -f docker-compose.dev.yml run --rm \
		-v ./tests/rag:/app/tests/rag:ro \
		backend python /app/tests/rag/evaluate_rag.py
