"""M2 exit check (handoff task 7): seed a book, insert a chunk with a 768-dim
vector, SELECT it back, confirm the round-trip — plus the schema properties
the design leans on (generated tsv over context_prefix || content, cosine
distance, JSONB codec).

Needs a pgvector Postgres reachable via TEST_DATABASE_URL, e.g.:
    docker run -d --name rag-pgvector-test -p 5433:5432 \
        -e POSTGRES_PASSWORD=test -e POSTGRES_DB=rag pgvector/pgvector:pg16
    TEST_DATABASE_URL=postgresql://postgres:test@localhost:5433/rag poetry run pytest
Skips cleanly when the env var is absent (unit-test-only CI lanes).
"""

import math
import os
import pathlib

import asyncpg
import pytest

from app.core.config import get_settings
from app.db import connection
from app.db.repositories import BookRepository, ChapterRepository, ChunkRepository
from app.db.rows import BookRow, ChapterRow, ChunkRow

TEST_DSN = os.environ.get("TEST_DATABASE_URL")
SCHEMA = pathlib.Path(__file__).parents[1] / "app" / "db" / "schema.sql"

pytestmark = pytest.mark.skipif(
    TEST_DSN is None, reason="TEST_DATABASE_URL not set — no pgvector Postgres available"
)

DIM = 768
UNIT_VEC = [1.0 / math.sqrt(DIM)] * DIM  # L2-normalized, as ingestion will store


@pytest.fixture
async def pool(monkeypatch: pytest.MonkeyPatch):
    # Bootstrap schema with a vanilla connection: register_vector (pool init)
    # would fail before CREATE EXTENSION vector has ever run.
    boot = await asyncpg.connect(dsn=TEST_DSN)
    try:
        await boot.execute(SCHEMA.read_text())
        await boot.execute("DELETE FROM books WHERE book_id = 'test-astro-part1'")
    finally:
        await boot.close()

    monkeypatch.setenv("DB_MODE", "direct")
    monkeypatch.setenv("DATABASE_URL", TEST_DSN)
    get_settings.cache_clear()
    yield await connection.get_pool()
    await connection.close_pool()
    get_settings.cache_clear()


async def test_book_chunk_roundtrip(pool):
    books = BookRepository(pool)
    chapters = ChapterRepository(pool)
    chunks = ChunkRepository(pool)

    await books.insert(BookRow(
        book_id="test-astro-part1",
        title="Astronomy 2e — Part I",
        author="Fraknoi, Morrison, Wolff",
        year=2026,
        gcs_uri="gs://test-bucket/astronomy-2e-part1.pdf",
        page_count=300,
        source="openstax",
    ))
    assert (await books.get("test-astro-part1")).title == "Astronomy 2e — Part I"
    assert any(b.book_id == "test-astro-part1" for b in await books.list_all())

    chapter_id = await chapters.insert(ChapterRow(
        book_id="test-astro-part1",
        ordinal=22,
        title="Chapter 22: Stars from Adolescence to Old Age",
        start_page=201,
        end_page=230,
    ))

    chunk_id = await chunks.insert(ChunkRow(
        book_id="test-astro-part1",
        chapter_id=chapter_id,
        page=205,
        bbox={"x0": 0.1, "y0": 0.2, "x1": 0.9, "y1": 0.4},
        modality="text",
        content="Main-sequence stars fuse hydrogen into helium in their cores.",
        context_prefix="From Chapter 22, on stellar evolution after the main sequence.",
        embedding=UNIT_VEC,
        token_count=14,
    ))

    got = await chunks.get(chunk_id)
    assert got is not None
    assert got.bbox == {"x0": 0.1, "y0": 0.2, "x1": 0.9, "y1": 0.4}  # JSONB codec
    assert len(got.embedding) == DIM
    assert all(
        math.isclose(a, b, rel_tol=1e-6) for a, b in zip(got.embedding, UNIT_VEC, strict=True)
    )

    async with pool.acquire() as conn:
        # cosine distance to itself ~ 0 → vector codec + <=> operator work
        dist = await conn.fetchval(
            "SELECT embedding <=> $1 FROM chunks WHERE chunk_id = $2", UNIT_VEC, chunk_id
        )
        assert dist == pytest.approx(0.0, abs=1e-6)

        # generated tsv indexes BOTH the verbatim content and the context
        # prefix — the "contextual BM25" property the M3 design relies on
        for term in ("hydrogen", "evolution"):
            hit = await conn.fetchval(
                "SELECT content_tsv @@ plainto_tsquery('english', $1) "
                "FROM chunks WHERE chunk_id = $2",
                term, chunk_id,
            )
            assert hit is True, f"tsv should match {term!r}"

    assert await chunks.delete_by_book("test-astro-part1") == 1
