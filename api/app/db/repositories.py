"""Repository classes: the only place SQL lives (phase2-selfbuilt.md §2.5).

Each method takes/returns Pydantic row models from rows.py. The retriever
service (services/retrieval/pgvector.py, M4+) holds repository instances
and never sees SQL.
"""

import asyncpg

from app.db.rows import BookRow, ChapterRow, ChunkRow, SearchHit

_CHUNK_COLUMNS = """
    chunk_id, book_id, chapter_id, page, bbox, modality,
    content, context_prefix, embedding, token_count, created_at
"""

# Hybrid BM25 + vector + RRF(k=60) — phase2-selfbuilt.md §5.1.
# $1 query embedding (vector), $2 query text, $3 top_k, $4 book_ids or NULL.
HYBRID_SEARCH_SQL = """
WITH vec AS (
  SELECT chunk_id, 1 - (embedding <=> $1) AS score
  FROM chunks
  WHERE ($4::text[] IS NULL OR book_id = ANY($4::text[]))
  ORDER BY embedding <=> $1
  LIMIT 40
),
bm AS (
  SELECT chunk_id, ts_rank_cd(content_tsv, plainto_tsquery('english', $2)) AS score
  FROM chunks
  WHERE ($4::text[] IS NULL OR book_id = ANY($4::text[]))
    AND content_tsv @@ plainto_tsquery('english', $2)
  ORDER BY score DESC
  LIMIT 40
),
fused AS (
  SELECT chunk_id, SUM(1.0 / (60 + rank)) AS rrf_score
  FROM (
    SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank FROM vec
    UNION ALL
    SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank FROM bm
  ) t
  GROUP BY chunk_id
)
SELECT c.chunk_id, c.book_id, c.page, c.bbox, c.modality,
       c.content, c.context_prefix,
       b.title AS book_title, b.author,
       ch.ordinal AS chapter_num, ch.title AS chapter_title,
       fused.rrf_score
FROM fused
JOIN chunks c   USING (chunk_id)
JOIN books  b   ON b.book_id = c.book_id
LEFT JOIN chapters ch ON ch.chapter_id = c.chapter_id
ORDER BY fused.rrf_score DESC
LIMIT $3
"""


class BookRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def insert(self, book: BookRow) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO books
                       (book_id, title, author, year, gcs_uri,
                        page_count, source, content_hash)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   ON CONFLICT (book_id) DO UPDATE SET
                       title = EXCLUDED.title,
                       author = EXCLUDED.author,
                       year = EXCLUDED.year,
                       gcs_uri = EXCLUDED.gcs_uri,
                       page_count = EXCLUDED.page_count,
                       source = EXCLUDED.source,
                       content_hash = EXCLUDED.content_hash,
                       ingested_at = now()""",
                book.book_id, book.title, book.author, book.year, book.gcs_uri,
                book.page_count, book.source, book.content_hash,
            )

    async def get(self, book_id: str) -> BookRow | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM books WHERE book_id = $1", book_id)
            return BookRow.model_validate(dict(row)) if row else None

    async def list_all(self) -> list[BookRow]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM books ORDER BY book_id")
            return [BookRow.model_validate(dict(r)) for r in rows]


class ChapterRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def insert(self, chapter: ChapterRow) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO chapters (book_id, ordinal, title, start_page, end_page)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (book_id, ordinal) DO UPDATE SET
                       title = EXCLUDED.title,
                       start_page = EXCLUDED.start_page,
                       end_page = EXCLUDED.end_page
                   RETURNING chapter_id""",
                chapter.book_id, chapter.ordinal, chapter.title,
                chapter.start_page, chapter.end_page,
            )
            assert row is not None  # INSERT … RETURNING always yields a row
            return int(row["chapter_id"])


class ChunkRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def insert(self, chunk: ChunkRow) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""INSERT INTO chunks
                        (book_id, chapter_id, page, bbox, modality,
                         content, context_prefix, embedding, token_count)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING {_CHUNK_COLUMNS}""",
                chunk.book_id, chunk.chapter_id, chunk.page, chunk.bbox,
                chunk.modality, chunk.content, chunk.context_prefix,
                chunk.embedding, chunk.token_count,
            )
            assert row is not None  # INSERT … RETURNING always yields a row
            return int(row["chunk_id"])

    async def get(self, chunk_id: int) -> ChunkRow | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_CHUNK_COLUMNS} FROM chunks WHERE chunk_id = $1", chunk_id
            )
            return ChunkRow.model_validate(dict(row)) if row else None

    async def insert_many(
        self,
        chunks: list[ChunkRow],
        conn: "asyncpg.Connection | asyncpg.pool.PoolConnectionProxy",
    ) -> int:
        """Bulk insert on a caller-provided connection so ingestion can wrap
        delete_by_book + insert_many in ONE transaction (§4.5: the book is
        the transaction boundary)."""
        await conn.executemany(
            """INSERT INTO chunks
                   (book_id, chapter_id, page, bbox, modality,
                    content, context_prefix, embedding, token_count)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            [
                (c.book_id, c.chapter_id, c.page, c.bbox, c.modality,
                 c.content, c.context_prefix, c.embedding, c.token_count)
                for c in chunks
            ],
        )
        return len(chunks)

    async def delete_by_book(self, book_id: str) -> int:
        """Idempotent re-ingest support (§4.5): book is the transaction boundary."""
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM chunks WHERE book_id = $1", book_id)
            return int(result.removeprefix("DELETE "))

    async def hybrid_search(
        self, query_vec: list[float], query_text: str, top_k: int = 20,
        book_ids: list[str] | None = None,
    ) -> list[SearchHit]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                HYBRID_SEARCH_SQL, query_vec, query_text, top_k, book_ids
            )
            return [SearchHit.model_validate(dict(r)) for r in rows]
