from pydantic import Field

from app.models.book import ApiModel


class BoundingBox(ApiModel):
    x0: float
    y0: float
    x1: float
    y1: float


class Citation(ApiModel):
    """Citation surfaced to the Angular client — a user-facing, 1-indexed reference."""

    index: int = Field(..., ge=1)
    book_id: str
    book_title: str
    author: str
    chapter_num: int | None = None
    chapter_title: str | None = None
    page: int = Field(..., ge=1)
    snippet: str
    bbox: BoundingBox | None = None


class RetrievedChunk(ApiModel):
    """Retriever-internal representation. Converted to Citation before sending to the UI."""

    chunk_id: str
    book_id: str
    book_title: str
    author: str
    chapter_num: int | None = None
    chapter_title: str | None = None
    page: int
    content: str
    score: float
    modality: str = "text"
    bbox: BoundingBox | None = None
