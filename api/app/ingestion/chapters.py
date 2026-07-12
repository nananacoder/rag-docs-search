"""Chapter detection (§4.1).

Primary (local-PDF path): the PDF's bookmark outline — OpenStax 2e ships a
complete TOC (level-1 "Chapter N Title" entries with exact start pages).
Verified against the real book: the body text never renders "Chapter N:
Title" as a heading block, so regex-over-blocks CANNOT work there; it
stays as the fallback for outline-less PDFs and the Document AI path.
"""

import itertools
import re

import fitz  # pymupdf

from app.core.logging import get_logger
from app.db.rows import ChapterRow
from app.ingestion.blocks import Block

log = get_logger(__name__)

_TOC_CHAPTER_RE = re.compile(r"^chapter\s+(\d+)\s*[:.]?\s*(.*)$", re.IGNORECASE)
_TOC_APPENDIX_RE = re.compile(r"^appendix\s+([A-Z])\s*[:.]?\s*(.*)$", re.IGNORECASE)
_APPENDIX_BASE = 1000  # appendices sort after numbered chapters


def chapters_from_toc(pdf_path: str, book_id: str) -> list[ChapterRow]:
    """Chapters from the PDF bookmark outline (level-1 entries)."""
    with fitz.open(pdf_path) as doc:
        toc = doc.get_toc()
    found: list[ChapterRow] = []
    for level, title, page in toc:
        if level != 1:
            continue
        text = title.strip()
        ordinal: int | None = None
        if m := _TOC_CHAPTER_RE.match(text):
            ordinal = int(m.group(1))
        elif a := _TOC_APPENDIX_RE.match(text):
            ordinal = _APPENDIX_BASE + (ord(a.group(1).upper()) - ord("A"))
        if ordinal is None:
            continue
        found.append(ChapterRow(
            book_id=book_id, ordinal=ordinal, title=text, start_page=page
        ))
    found.sort(key=lambda c: c.start_page or 0)
    for cur, nxt in itertools.pairwise(found):
        cur.end_page = (nxt.start_page or 1) - 1
    log.info("chapters_from_toc", count=len(found))
    return found

_CHAPTER_RE = re.compile(r"^(?:chapter\s+(\d+))\b[.:\s]*(.*)$", re.IGNORECASE)
_APPENDIX_RE = re.compile(r"^appendix\s+([A-Z])\b[.:\s]*(.*)$", re.IGNORECASE)
_MAX_HEADING_WORDS = 12


def detect_chapters(blocks: list[Block], book_id: str) -> list[ChapterRow]:
    """Fallback: ChapterRows from heading blocks (outline-less PDFs, DocAI)."""
    found: list[ChapterRow] = []
    seen_ordinals: set[int] = set()
    appendix_base = _APPENDIX_BASE

    for block in blocks:
        text = block.text.strip()
        if len(text.split()) > _MAX_HEADING_WORDS:
            continue  # prose mentioning "Chapter 5" — not a heading
        is_headingish = block.block_type in ("heading-1", "heading-2")
        m = _CHAPTER_RE.match(text)
        ordinal: int | None = None
        title = text
        if m:
            ordinal = int(m.group(1))
        elif (a := _APPENDIX_RE.match(text)) and is_headingish:
            ordinal = appendix_base + (ord(a.group(1).upper()) - ord("A"))
        if ordinal is None or ordinal in seen_ordinals:
            continue
        # Plain-text chapter matches must also look like headings when the
        # parser gives us layout types; text-only fallback accepts the regex.
        if block.block_type == "text" and not m:
            continue
        seen_ordinals.add(ordinal)
        found.append(ChapterRow(
            book_id=book_id, ordinal=ordinal, title=title, start_page=block.page
        ))

    found.sort(key=lambda c: c.start_page or 0)
    for cur, nxt in itertools.pairwise(found):
        cur.end_page = (nxt.start_page or 1) - 1
    log.info("chapters_detected", count=len(found))
    return found


def chapter_for_page(chapters: list[ChapterRow], page: int) -> ChapterRow | None:
    """The chapter whose [start_page, end_page] covers `page` (None before ch.1)."""
    hit = None
    for ch in chapters:
        if (
            ch.start_page is not None
            and ch.start_page <= page
            and (ch.end_page is None or page <= ch.end_page)
        ):
            hit = ch
    return hit
