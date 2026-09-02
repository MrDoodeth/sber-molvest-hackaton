from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.database import create_database
from app.providers.docling import DoclingHybridParser
from app.providers.embeddings import BgeM3EmbeddingProvider
from app.providers.gigachat import GigaChatProvider
from app.providers.interfaces import (
    EmbeddingProvider,
    LLMProvider,
    ObjectStorage,
    PermanentDocumentParser,
    VectorStore,
)
from app.providers.storage import LocalObjectStorage, S3ObjectStorage
from app.providers.vector import QdrantHybridVectorStore
from app.services.admin import AdminService
from app.services.attachments import AttachmentService
from app.services.broker import EventBroker
from app.services.context import ContextBuilder
from app.services.dialogs import DialogService
from app.services.generation_context import GenerationContextService
from app.services.kb import KnowledgeBaseService
from app.services.moderation import ModerationService
from app.services.rag import RAGService
from app.services.settings import PromptService, SettingsService
from app.services.tasks import TaskSupervisor


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    storage: ObjectStorage
    llm_provider: LLMProvider
    embedding_provider: EmbeddingProvider
    vector_store: VectorStore
    document_parser: PermanentDocumentParser
    broker: EventBroker
    tasks: TaskSupervisor
    settings_service: SettingsService
    prompt_service: PromptService
    attachment_service: AttachmentService
    rag_service: RAGService
    knowledge_base: KnowledgeBaseService
    dialogs: DialogService
    moderation: ModerationService
    admin: AdminService


def build_container(
    settings: Settings,
    *,
    llm_provider: LLMProvider | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
    document_parser: PermanentDocumentParser | None = None,
    storage: ObjectStorage | None = None,
) -> ApplicationContainer:
    engine, session_factory = create_database(settings.database_url)
    actual_llm = llm_provider or GigaChatProvider(settings)
    actual_embedding = embedding_provider or BgeM3EmbeddingProvider(
        settings.embedding_device,
        model_path=settings.embedding_model_path,
    )
    actual_vector = vector_store or QdrantHybridVectorStore(
        settings.qdrant_url,
        settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
    )
    actual_parser = document_parser or DoclingHybridParser(
        model_path=settings.embedding_model_path
    )
    if storage is not None:
        actual_storage = storage
    elif settings.storage_backend == "s3":
        if settings.s3_access_key_id is None or settings.s3_secret_access_key is None:
            raise ValueError("S3 credentials are required")
        actual_storage = S3ObjectStorage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id.get_secret_value(),
            secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            use_ssl=settings.s3_use_ssl,
        )
    else:
        actual_storage = LocalObjectStorage(settings.local_storage_path)
    broker = EventBroker()
    tasks = TaskSupervisor()
    settings_service = SettingsService()
    prompt_service = PromptService()
    attachment_service = AttachmentService(actual_storage, actual_llm, settings)
    rag_service = RAGService(actual_embedding, actual_vector)
    context_builder = ContextBuilder()
    generation_context = GenerationContextService(
        session_factory=session_factory,
        attachment_service=attachment_service,
        context_builder=context_builder,
        rag_service=rag_service,
        llm_provider=actual_llm,
    )
    knowledge_base = KnowledgeBaseService(
        session_factory=session_factory,
        storage=actual_storage,
        parser=actual_parser,
        embedding_provider=actual_embedding,
        vector_store=actual_vector,
        tasks=tasks,
    )
    dialogs = DialogService(
        session_factory=session_factory,
        attachment_service=attachment_service,
        settings_service=settings_service,
        prompt_service=prompt_service,
        generation_context=generation_context,
        llm_provider=actual_llm,
        broker=broker,
        tasks=tasks,
    )
    moderation = ModerationService(
        session_factory=session_factory,
        knowledge_base=knowledge_base,
        attachment_service=attachment_service,
        settings_service=settings_service,
        prompt_service=prompt_service,
        generation_context=generation_context,
        llm_provider=actual_llm,
    )
    return ApplicationContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        storage=actual_storage,
        llm_provider=actual_llm,
        embedding_provider=actual_embedding,
        vector_store=actual_vector,
        document_parser=actual_parser,
        broker=broker,
        tasks=tasks,
        settings_service=settings_service,
        prompt_service=prompt_service,
        attachment_service=attachment_service,
        rag_service=rag_service,
        knowledge_base=knowledge_base,
        dialogs=dialogs,
        moderation=moderation,
        admin=AdminService(session_factory, settings_service, prompt_service),
    )
