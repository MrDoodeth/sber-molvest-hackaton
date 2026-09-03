from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    label: str
    api_model_id: str
    context_limit: int
    supports_images: bool = True
    supports_structured_output: bool = True


# Model identifiers are part of the frontend/backend contract. Context limits live
# here so neither services nor the SPA need to duplicate model knowledge.
MODEL_CAPABILITIES: dict[str, ModelCapabilities] = {
    "GigaChat-2": ModelCapabilities("Lite", "GigaChat-2", 128_000),
    "GigaChat-2-Pro": ModelCapabilities("Pro", "GigaChat-2-Pro", 128_000),
    "GigaChat-2-Max": ModelCapabilities("Max", "GigaChat-2-Max", 128_000),
    "GigaChat-3-Ultra": ModelCapabilities("Ultra", "GigaChat-3-Ultra", 128_000),
}

EMBEDDING_MODEL_ID = "BAAI/bge-m3"
EMBEDDING_DIMENSION = 1024
EMBEDDING_CONTEXT_LIMIT = 8192
QDRANT_COLLECTION = "knowledge_chunks"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Molvest 1C Support"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://molvest:molvest@localhost:5432/molvest"
    seed_on_startup: bool = True

    jwt_secret: SecretStr = SecretStr("local-development-secret-change-in-production")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_ttl_minutes: int = Field(default=480, ge=1)
    auth_cookie_name: str = "molvest_session"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict"] = "lax"
    demo_auth_enabled: bool = False

    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    sse_heartbeat_seconds: float = Field(default=15.0, gt=0)
    dialog_idle_timeout_hours: float = Field(default=24.0, gt=0)
    dialog_idle_scan_seconds: float = Field(default=300.0, gt=0)

    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: Path = Path("./var/storage")
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "molvest"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_use_ssl: bool = True

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    embedding_device: str = "cpu"
    embedding_model_path: Path = Path("/opt/models/bge-m3")
    docling_artifacts_path: Path | None = None

    gigachat_credentials: SecretStr | None = None
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_ca_bundle_file: Path | None = None
    gigachat_max_retries: int = Field(default=3, ge=0)
    gigachat_retry_backoff_factor: float = Field(default=0.5, ge=0)

    runtime_image_max_bytes: int = 15 * 1024 * 1024
    runtime_document_max_bytes: int = 40 * 1024 * 1024
    permanent_document_max_bytes: int = 40 * 1024 * 1024

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_security(self) -> Settings:
        if "*" in self.cors_origins:
            raise ValueError("CORS wildcard is incompatible with credentialed cookies")
        if self.environment == "production":
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production")
            if self.jwt_secret.get_secret_value().startswith("local-development"):
                raise ValueError("JWT_SECRET must be configured in production")
        if self.storage_backend == "s3" and (
            self.s3_access_key_id is None or self.s3_secret_access_key is None
        ):
            raise ValueError("S3 credentials are required when STORAGE_BACKEND=s3")
        return self
