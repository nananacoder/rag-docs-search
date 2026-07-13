"""Ingestion orchestrator (§4): parse → chapters → chunk → caption →
contextualize → embed → single-transaction upsert.

CLI (free dry run, no GCP calls):
    poetry run python -m app.ingestion.pipeline \
        --pdf ../astronomy-2e.pdf --book-id astro-2e --title "Astronomy 2e" \
        --author "Fraknoi, Morrison, Wolff" --dry-run

Full run (paid: Document AI + Gemini + embedding; Cloud SQL must be started):
    drop --dry-run, add --gcs-uri gs://…/astronomy-2e.pdf to use Document AI
    (otherwise the pymupdf fallback parses the local file, text-only).
"""

import argparse
import asyncio
from collections import defaultdict

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db import connection
from app.db.repositories import BookRepository, ChapterRepository, ChunkRepository
from app.db.rows import BookRow, ChapterRow, ChunkRow
from app.ingestion.blocks import Block
from app.ingestion.captioner import Captioner
from app.ingestion.chapters import chapter_for_page, chapters_from_toc, detect_chapters
from app.ingestion.chunker import ChunkDraft, chunk_blocks
from app.ingestion.contextualizer import Contextualizer
from app.ingestion.embedder import Embedder
from app.ingestion.parser import DocumentAIParser, PymupdfParser

log = get_logger(__name__)

_MAX_CHAPTER_CONTEXT_CHARS = 400_000  # ~100K tokens, well inside Flash's window


def build_chapter_texts(blocks: list[Block], chapters: list[ChapterRow]) -> dict[int, str]:
    """ordinal → concatenated chapter text, for the contextualizer prompt."""
    texts: dict[int, list[str]] = defaultdict(list)
    for b in blocks:
        if b.block_type not in ("text", "heading-1", "heading-2"):
            continue
        ch = chapter_for_page(chapters, b.page)
        if ch is not None:
            texts[ch.ordinal].append(b.text)
    return {
        ordinal: "\n".join(parts)[:_MAX_CHAPTER_CONTEXT_CHARS]
        for ordinal, parts in texts.items()
    }


class IngestionPipeline:
    """Stages are injected so tests run with fakes and zero paid calls."""

    def __init__(
        self,
        settings: Settings,
        contextualizer: Contextualizer | None = None,
        captioner: Captioner | None = None,
        embedder: Embedder | None = None,
        skip_context: bool = False,
    ) -> None:
        self.settings = settings
        self.contextualizer = contextualizer
        self.captioner = captioner
        self.embedder = embedder
        self.skip_context = skip_context

    async def build_chunks(
        self, blocks: list[Block], book: BookRow,
        chapters: list[ChapterRow] | None = None,
    ) -> tuple[list[ChapterRow], list[ChunkRow]]:
        """Everything up to (but excluding) the DB write. Pure given fakes.

        `chapters` from the PDF outline when available (local-PDF path);
        falls back to heading-block detection otherwise.
        """
        if chapters is None:
            chapters = detect_chapters(blocks, book.book_id)
        drafts = chunk_blocks(
            blocks, chapters,
            self.settings.chunk_size_tokens, self.settings.chunk_overlap_tokens,
        )
        drafts = await self._caption_figures(drafts)
        chapter_texts = build_chapter_texts(blocks, chapters)
        prefixes = await self._contextualize(drafts, chapter_texts)
        embeddings = await self._embed(drafts, prefixes)

        rows = [
            ChunkRow(
                book_id=book.book_id,
                chapter_id=None,  # resolved to real FK ids at upsert time
                page=d.page, bbox=d.bbox, modality=d.modality,
                content=d.content, context_prefix=prefix,
                embedding=vec, token_count=d.token_count,
            )
            for d, prefix, vec in zip(drafts, prefixes, embeddings, strict=True)
        ]
        # stash ordinal → row mapping for FK resolution
        self._ordinals = [d.chapter_ordinal for d in drafts]
        return chapters, rows

    async def _caption_figures(self, drafts: list[ChunkDraft]) -> list[ChunkDraft]:
        sem = asyncio.Semaphore(4)  # 8 brushed Vertex RPM quota (429s)

        async def one(d: ChunkDraft) -> ChunkDraft:
            if d.modality != "figure" or d.image_bytes is None:
                return d
            if self.captioner is None:
                return d.model_copy(update={"content": "", "image_bytes": None})
            async with sem:
                caption = await self.captioner.caption(d.image_bytes, d.image_mime)
            return d.model_copy(update={"content": caption, "image_bytes": None})

        captioned = await asyncio.gather(*(one(d) for d in drafts))
        return [d for d in captioned if d.content.strip()]

    async def _contextualize(
        self, drafts: list[ChunkDraft], chapter_texts: dict[int, str]
    ) -> list[str | None]:
        if self.skip_context or self.contextualizer is None:
            return [None] * len(drafts)
        # Concurrency bounded low and drafts kept in chapter order: in-flight
        # calls mostly share one chapter prefix, keeping Gemini's implicit
        # prompt cache hot (the cost model relies on it).
        sem = asyncio.Semaphore(4)  # 8 brushed Vertex RPM quota (429s)

        async def one(d: ChunkDraft) -> str | None:
            chapter_text = chapter_texts.get(d.chapter_ordinal or -1, "")
            if not chapter_text:
                return None
            assert self.contextualizer is not None
            async with sem:
                return await self.contextualizer.contextualize(d.content, chapter_text)

        return list(await asyncio.gather(*(one(d) for d in drafts)))

    async def _embed(
        self, drafts: list[ChunkDraft], prefixes: list[str | None]
    ) -> list[list[float] | None]:
        if self.embedder is None:
            return [None] * len(drafts)
        # embed the same concatenation the generated content_tsv indexes
        texts = [
            f"{p} {d.content}" if p else d.content
            for d, p in zip(drafts, prefixes, strict=True)
        ]
        return list(await self.embedder.embed(texts))

    async def upsert(
        self, book: BookRow, chapters: list[ChapterRow], rows: list[ChunkRow]
    ) -> int:
        pool = await connection.get_pool()
        await BookRepository(pool).insert(book)
        chapter_repo = ChapterRepository(pool)
        id_by_ordinal = {
            ch.ordinal: await chapter_repo.insert(ch) for ch in chapters
        }
        for row, ordinal in zip(rows, self._ordinals, strict=True):
            row.chapter_id = id_by_ordinal.get(ordinal) if ordinal is not None else None
        chunk_repo = ChunkRepository(pool)
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("DELETE FROM chunks WHERE book_id = $1", book.book_id)
            inserted = await chunk_repo.insert_many(rows, conn)
        log.info("book_ingested", book_id=book.book_id, chunks=inserted)
        return inserted


async def _main() -> None:
    ap = argparse.ArgumentParser(description="Ingest a PDF into the Phase 2 index")
    ap.add_argument("--pdf", help="local PDF path (pymupdf parse)")
    ap.add_argument("--gcs-uri", help="GCS PDF URI (Document AI batch parse)")
    ap.add_argument("--book-id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="parse+chunk only: no LLM calls, no DB writes, print stats")
    ap.add_argument("--no-context", action="store_true",
                    help="skip Contextual Retrieval prefixes (not recommended)")
    args = ap.parse_args()

    settings = get_settings()
    toc_chapters: list[ChapterRow] | None = None
    if args.gcs_uri:
        assert settings.docai_processor_name and settings.docai_gcs_output_prefix, \
            "DOCAI_PROCESSOR_NAME + DOCAI_GCS_OUTPUT_PREFIX required for --gcs-uri"
        blocks = DocumentAIParser(
            settings.docai_processor_name, settings.docai_gcs_output_prefix
        ).parse_gcs(args.gcs_uri)
        if args.pdf:  # local copy available → outline is the better chapter source
            toc_chapters = chapters_from_toc(args.pdf, args.book_id) or None
    else:
        assert args.pdf, "--pdf or --gcs-uri required"
        # Route B+: free pymupdf text AND embedded-image extraction
        blocks = PymupdfParser().parse(args.pdf, extract_images=not args.dry_run)
        toc_chapters = chapters_from_toc(args.pdf, args.book_id) or None

    book = BookRow(
        book_id=args.book_id, title=args.title, author=args.author,
        year=args.year, gcs_uri=args.gcs_uri or f"file://{args.pdf}",
        source="openstax",
    )

    if args.dry_run:
        pipe = IngestionPipeline(settings, skip_context=True)
        chapters, rows = await pipe.build_chunks(blocks, book, chapters=toc_chapters)
        by_mod: dict[str, int] = defaultdict(int)
        for r in rows:
            by_mod[r.modality] += 1
        toks = [r.token_count or 0 for r in rows]
        print(f"blocks={len(blocks)} chapters={len(chapters)} chunks={len(rows)}")
        print(f"by modality: {dict(by_mod)}")
        if toks:
            print(f"token_count p50={sorted(toks)[len(toks)//2]} max={max(toks)}")
        return

    pipe = IngestionPipeline(
        settings,
        contextualizer=None if args.no_context else Contextualizer(settings),
        captioner=Captioner(settings),
        embedder=Embedder(settings),
        skip_context=args.no_context,
    )
    chapters, rows = await pipe.build_chunks(blocks, book, chapters=toc_chapters)
    inserted = await pipe.upsert(book, chapters, rows)
    print(f"ingested {inserted} chunks for {book.book_id}")
    await connection.close_pool()


if __name__ == "__main__":
    asyncio.run(_main())
