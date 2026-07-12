"""Repository classes: the only place SQL lives (phase2-selfbuilt.md §2.5).

Each method takes/returns Pydantic row models from rows.py. The retriever
service (services/retrieval/pgvector.py, M4+) holds repository instances
and never sees SQL.
"""

import asyncpg

from app.db.rows import BookRow, ChapterRow, ChunkRow

_CHUNK_COLUMNS = """
    chunk_id, book_id, chapter_id, page, bbox, modality,
    content, context_prefix, embedding, token_count, created_at
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
    ) -> list[ChunkRow]:
        """Hybrid BM25 + vector + RRF — phase2-selfbuilt.md §5.1. Lands in M4."""
        raise NotImplementedError("hybrid_search is an M4 deliverable (see §5.1)")
