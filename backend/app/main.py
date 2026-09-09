from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.openapi import OPENAPI_TAGS
from app.api.router import api_router
from app.core.config import Settings
from app.core.errors import install_error_handlers
from app.models import Base
from app.services.container import ApplicationContainer, build_container
from app.services.seeds import seed_defaults


def create_app(
    settings: Settings | None = None,
    container: ApplicationContainer | None = None,
) -> FastAPI:
    actual_settings = settings or Settings()
    actual_container = container or build_container(actual_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with actual_container.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        if actual_settings.seed_on_startup:
            await seed_defaults(actual_container.session_factory)
        warmup = getattr(actual_container.embedding_provider, "warmup", None)
        if callable(warmup):
            await warmup()
        parser_warmup = getattr(actual_container.document_parser, "warmup", None)
        if callable(parser_warmup):
            await parser_warmup()
        await actual_container.knowledge_base.recover_processing_documents()
        await actual_container.moderation.recover_closed_candidates()
        await actual_container.dialogs.recover_pending_turns()
        actual_container.tasks.spawn(
            actual_container.dialogs.close_idle_dialogs_loop(
                idle_after=timedelta(hours=actual_settings.dialog_idle_timeout_hours),
                scan_interval_seconds=actual_settings.dialog_idle_scan_seconds,
            ),
            cancel_on_shutdown=True,
        )
        try:
            yield
        finally:
            await actual_container.tasks.shutdown()
            parser_close = getattr(actual_container.document_parser, "close", None)
            if callable(parser_close):
                await parser_close()
            await actual_container.rag_cache.close()
            await actual_container.engine.dispose()

    app = FastAPI(
        title=actual_settings.app_name,
        version="0.1.0",
        description=(
            "Async FastAPI backend for the Molvest 1C support MVP: demo role context, "
            "dialogs and role-separated SSE, GigaChat generation, hybrid RAG, "
            "knowledge moderation and monitoring. REST JSON uses snake_case."
        ),
        openapi_tags=OPENAPI_TAGS,
        contact={"name": "Molvest Hackathon Backend Team"},
        license_info={"name": "Internal Hackathon MVP"},
        docs_url="/docs" if actual_settings.environment != "production" else None,
        redoc_url="/redoc" if actual_settings.environment != "production" else None,
        openapi_url=(
            "/openapi.json" if actual_settings.environment != "production" else None
        ),
        lifespan=lifespan,
    )
    app.state.container = actual_container
    install_error_handlers(app)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    if actual_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=actual_settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Last-Event-ID", "X-Molvest-Role"],
        )
    app.include_router(api_router)
    return app


app = create_app()
