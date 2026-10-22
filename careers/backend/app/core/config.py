import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_ENV_FILE, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "FairEnrol Careers"
    ENVIRONMENT: str = "development"
    APP_ENV: str | None = None
    APP_DEBUG: bool = True

    DATABASE_URL: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT_SECONDS: int = 10
    OUTBOX_PUBLISHER: str = "logging"
    OUTBOX_QUEUE_URL: str | None = None
    OUTBOX_PUBLISH_TIMEOUT_SECONDS: float = 5.0
    OUTBOX_BATCH_SIZE: int = 25
    OUTBOX_POLL_INTERVAL_SECONDS: float = 2.0
    OUTBOX_LEASE_SECONDS: int = 60
    OUTBOX_MAX_ATTEMPTS: int = 10
    OUTBOX_RETRY_BASE_DELAY_SECONDS: int = 5
    OUTBOX_RETRY_MAX_DELAY_SECONDS: int = 900
    OUTBOX_PUBLISHED_RETENTION_DAYS: int = 30
    OUTBOX_WORKER_ID: str | None = None
    OUTBOX_METRICS_PORT: int = 9101
    PROCESSING_WORKER_BATCH_SIZE: int = 5
    PROCESSING_WORKER_POLL_INTERVAL_SECONDS: float = 2.0
    PROCESSING_WORKER_LEASE_SECONDS: int = 900
    PROCESSING_WORKER_MAX_ATTEMPTS: int = 3
    PROCESSING_WORKER_RETRY_BASE_DELAY_SECONDS: int = 10
    PROCESSING_WORKER_RETRY_MAX_DELAY_SECONDS: int = 900
    PROCESSING_WORKER_ID: str | None = None
    PROCESSING_WORKER_METRICS_PORT: int = 9102
    AI_PROVIDER_MAX_CONCURRENCY: int = 1
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    STORAGE_BACKEND: str = "local"
    LOCAL_UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_UPLOAD_EXTENSIONS: str = ".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg"

    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_SESSION_TOKEN: str | None = None
    S3_BUCKET: str | None = None
    S3_ENDPOINT_URL: str | None = None
    S3_PUBLIC_BASE_URL: str | None = None

    AI_SERVICE_BASE_URL: str = "http://127.0.0.1:8010"
    AI_SERVICE_API_KEY: str | None = None
    AI_SERVICE_PARSE_TIMEOUT_SECONDS: int = 120
    AI_SERVICE_MATCH_TIMEOUT_SECONDS: int = 600

    @staticmethod
    def _parse_list(value: str) -> list[str]:
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return self._parse_list(self.BACKEND_CORS_ORIGINS)

    @property
    def runtime_environment(self) -> str:
        return (self.APP_ENV or self.ENVIRONMENT).strip().lower()

    @property
    def is_production_runtime(self) -> bool:
        return self.runtime_environment in {"production", "prod", "eks", "staging"}

    @property
    def allowed_upload_extensions(self) -> list[str]:
        return [extension.lower() for extension in self._parse_list(self.ALLOWED_UPLOAD_EXTENSIONS)]

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
