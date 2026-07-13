"""Phase 2 retriever: hybrid pgvector search + LLM rerank (§5).

Flow per query: embed query (cached) → hybrid BM25+vector+RRF top-20 in
one SQL round-trip → Gemini Flash rerank → top-k RetrievedChunks.
"""

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.connection import get_pool
from app.db.repositories import BookRepository, ChunkRepository
from app.db.rows import SearchHit
from app.ingestion.embedder import Embedder
from app.models.book import Book
from app.models.citation import BoundingBox, RetrievedChunk
from app.services.retrieval.base import Retriever
from app.services.retrieval.reranker import GeminiReranker

log = get_logger(__name__)

_FUSED_CANDIDATES = 20  # top-20 → rerank → top-k (§5.2)


class PgVectorRetriever(Retriever):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embedder = Embedder(settings)
        self.reranker = GeminiReranker(settings)

    async def list_books(self) -> list[Book]:
        pool = await get_pool()
        rows = await BookRepository(pool).list_all()
        return [
            Book(
                book_id=r.book_id, title=r.title, author=r.author, year=r.year,
                page_count=r.page_count or 0, gcs_uri=r.gcs_uri,
            )
            for r in rows
        ]

    async def retrieve(
        self, query: str, top_k: int, book_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        pool = await get_pool()
        query_vec = await self.embedder.embed_query(query)
        hits = await ChunkRepository(pool).hybrid_search(
            query_vec, query, top_k=_FUSED_CANDIDATES, book_ids=book_ids
        )
        log.info("hybrid_search_done", candidates=len(hits), query_len=len(query))
        kept = await self.reranker.rerank(query, hits, keep=top_k)
        return [self._to_chunk(h) for h in kept]

    @staticmethod
    def _to_chunk(h: SearchHit) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=str(h.chunk_id),
            book_id=h.book_id,
            book_title=h.book_title,
            author=h.author,
            chapter_num=h.chapter_num,
            chapter_title=h.chapter_title,
            page=h.page or 1,
            content=h.content,  # verbatim text only — prefix never shown to users
            score=h.rrf_score,
            modality=h.modality,
            bbox=BoundingBox(**h.bbox) if h.bbox else None,
        )
