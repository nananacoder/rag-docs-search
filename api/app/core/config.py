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

    # Phase 2 — Cloud SQL + pgvector (phase2-selfbuilt.md §2.5)
    # "cloudsql": cloud-sql-python-connector + IAM auth (Cloud Run, dev-against-cloud)
    # "direct":   plain asyncpg DSN (CI / local docker Postgres)
    db_mode: Literal["cloudsql", "direct"] = "cloudsql"
    db_instance: str = "rag-pg"
    db_name: str = "rag"
    db_iam_user: str | None = None
    database_url: str | None = None  # direct mode only
    db_pool_min_size: int = Field(default=2, ge=0)
    db_pool_max_size: int = Field(default=10, ge=1)

    # Phase 2 — ingestion pipeline (M3, phase2-selfbuilt.md §4)
    docai_processor_name: str | None = None  # projects/…/locations/…/processors/…
    docai_gcs_output_prefix: str | None = None  # gs://bucket/docai-out/ for batch parses
    # gemini-embedding-2(-preview) is allowlist-gated on this project as of
    # 2026-07 (404/FAILED_PRECONDITION, probed); 001 is the GA Gemini-family
    # model with the same MRL truncation mechanics. Revisit when 2 hits GA.
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768  # MRL truncation; pgvector HNSW caps at 2000
    embedding_batch_size: int = Field(default=250, ge=1, le=250)
    chunk_size_tokens: int = 800
    chunk_overlap_tokens: int = 120
    ingest_cache_dir: str = ".ingest_cache"  # embedding/caption cache (local JSON)

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

    @property
    def db_instance_connection_name(self) -> str:
        """PROJECT:REGION:INSTANCE, the Cloud SQL connector's addressing format."""
        if not self.gcp_project_id:
            raise ValueError("GCP_PROJECT_ID is required when DB_MODE=cloudsql")
        return f"{self.gcp_project_id}:{self.gcp_location}:{self.db_instance}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
