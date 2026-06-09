import json
import time
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import GeneratorDep, RetrieverDep, SettingsDep
from app.models.citation import Citation, RetrievedChunk
from app.models.query import (
    CitationsEvent,
    ErrorEvent,
    QueryDone,
    QueryRequest,
    TokenEvent,
)

router = APIRouter(tags=["query"])
log = structlog.get_logger(__name__)


def _chunks_to_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            index=i + 1,
            book_id=c.book_id,
            book_title=c.book_title,
            author=c.author,
            chapter_num=c.chapter_num,
            chapter_title=c.chapter_title,
            page=c.page,
            snippet=_make_snippet(c.content),
            bbox=c.bbox,
        )
        for i, c in enumerate(chunks)
    ]


def _make_snippet(text: str, max_chars: int = 240) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _sse(event: BaseModel) -> bytes:
    return f"data: {event.model_dump_json(by_alias=True)}\n\n".encode()


async def _stream_query(
    request: QueryRequest,
    retriever,
    generator,
    settings,
) -> AsyncIterator[bytes]:
    started = time.monotonic()
    top_k = request.top_k or settings.default_top_k
    top_k = min(top_k, settings.max_top_k)

    try:
        chunks = await retriever.retrieve(
            query=request.question,
            top_k=top_k,
            book_ids=request.book_ids,
        )
    except Exception as exc:  # noqa: BLE001 — surface any retriever error to UI
        log.exception("retrieval_failed", error=str(exc))
        yield _sse(ErrorEvent(message=f"Retrieval failed: {exc}"))
        return

    citations = _chunks_to_citations(chunks)
    yield _sse(CitationsEvent(citations=citations))

    try:
        async for token in generator.stream(request.question, chunks):
            if token:
                yield _sse(TokenEvent(text=token))
    except Exception as exc:  # noqa: BLE001
        log.exception("generation_failed", error=str(exc))
        yield _sse(ErrorEvent(message=f"Generation failed: {exc}"))
        return

    metrics = generator.last_metrics()
    total_ms = int((time.monotonic() - started) * 1000)
    yield _sse(
        QueryDone(
            input_tokens=metrics.input_tokens,
            output_tokens=metrics.output_tokens,
            total_ms=total_ms,
            model=metrics.model,
        ),
    )
    log.info(
        "query_complete",
        question_chars=len(request.question),
        book_filter=request.book_ids,
        retrieved=len(chunks),
        input_tokens=metrics.input_tokens,
        output_tokens=metrics.output_tokens,
        total_ms=total_ms,
        model=metrics.model,
    )


@router.post("/query")
async def query(
    request: QueryRequest,
    retriever: RetrieverDep,
    generator: GeneratorDep,
    settings: SettingsDep,
) -> StreamingResponse:
    return StreamingResponse(
        _stream_query(request, retriever, generator, settings),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
