from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

RetrievalBackend = Literal["mock", "discovery_engine", "pgvector"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    retrieval_backend: RetrievalBackend = "mock"

    gcp_project_id: str | None = None
    gcp_location: str = "us-central1"

    discovery_engine_datastore_id: str | None = None
    discovery_engine_engine_id: str | None = None
    discovery_engine_collection: str = "default_collection"
    discovery_engine_location: Literal["us", "eu", "global"] = "us"

    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-2.5-pro"
    generation_temperature: float = 0.2

    default_top_k: int = Field(default=5, ge=1, le=20)
    max_top_k: int = Field(default=20, ge=1, le=50)

    cors_origins: str = "http://localhost:4200"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_gcp_backend(self) -> bool:
        return self.retrieval_backend != "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
