"""Pydantic models mirroring DB rows (phase2-selfbuilt.md §2.5).

One modeling system across API + DB layers — these are the objects
repositories return and the retriever/generation code consumes. No ORM.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

Modality = Literal["text", "table", "figure", "diagram"]


class DbRow(BaseModel):
    """Base for DB row models: validate from asyncpg Records / attribute objects."""

    model_config = ConfigDict(from_attributes=True)


class BookRow(DbRow):
    book_id: str
    title: str
    author: str
    year: int | None = None
    gcs_uri: str
    page_count: int | None = None
    source: str | None = None
    ingested_at: datetime | None = None
    content_hash: str | None = None


class ChapterRow(DbRow):
    chapter_id: int | None = None  # None until inserted (BIGSERIAL)
    book_id: str
    ordinal: int
    title: str | None = None
    start_page: int | None = None
    end_page: int | None = None


class SearchHit(DbRow):
    """One hybrid-search result row: chunk + joined book/chapter metadata
    + RRF score (phase2-selfbuilt.md §5.1)."""

    chunk_id: int
    book_id: str
    book_title: str
    author: str
    chapter_num: int | None = None
    chapter_title: str | None = None
    page: int | None = None
    bbox: dict[str, Any] | None = None
    modality: str = "text"
    content: str
    context_prefix: str | None = None
    rrf_score: float


class ChunkRow(DbRow):
    chunk_id: int | None = None  # None until inserted (BIGSERIAL)
    book_id: str
    chapter_id: int | None = None
    page: int | None = None
    bbox: dict[str, Any] | None = None
    modality: Modality = "text"
    content: str
    # M3 Contextual Retrieval: LLM-generated situating context. Embedding and
    # the generated content_tsv cover context_prefix || content; citations
    # display bare content.
    context_prefix: str | None = None
    embedding: list[float] | None = None
    token_count: int | None = None
    created_at: datetime | None = None

    @field_validator("embedding", mode="before")
    @classmethod
    def _coerce_vector(cls, v: Any) -> Any:
        # pgvector.asyncpg decodes vector columns to a pgvector.Vector
        # (numpy array in older versions) — pydantic won't accept either
        # as list[float], so coerce here once.
        if v is None or isinstance(v, list):
            return v
        if hasattr(v, "to_list"):
            return v.to_list()
        return [float(x) for x in v]
