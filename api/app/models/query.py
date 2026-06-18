from typing import Annotated, Literal

from pydantic import Field

from app.models.book import ApiModel
from app.models.citation import Citation


class QueryRequest(ApiModel):
    question: Annotated[str, Field(min_length=1, max_length=2000)]
    book_ids: Annotated[
        list[str] | None,
        Field(description="If set, scope retrieval to these books."),
    ] = None
    top_k: Annotated[int | None, Field(ge=1, le=20)] = None


# --- SSE events ---------------------------------------------------------------


class CitationsEvent(ApiModel):
    type: Literal["citations"] = "citations"
    citations: list[Citation]


class TokenEvent(ApiModel):
    type: Literal["token"] = "token"
    text: str


class QueryDone(ApiModel):
    type: Literal["done"] = "done"
    input_tokens: int
    output_tokens: int
    total_ms: int
    model: str


class ErrorEvent(ApiModel):
    type: Literal["error"] = "error"
    message: str


QueryEvent = Annotated[
    CitationsEvent | TokenEvent | QueryDone | ErrorEvent,
    Field(discriminator="type"),
]
