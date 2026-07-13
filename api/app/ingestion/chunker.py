"""Chapter-aware chunking (§4.2).

- text blocks: recursive splitter, chunk_size=800 tokens, overlap=120
- table blocks: one chunk per table (long tables split upstream)
- figure/caption blocks: one chunk each, content filled by the captioner
- list-item blocks: skipped from the main index (structural-noise filter —
  the Phase 1 "Key Terms outranks body text" failure)
- chunks NEVER span chapter boundaries

Token counting uses the ~4 chars/token heuristic — chunk size is a tuning
knob validated against the eval set (M5), not a hard budget.
"""

from typing import Any

from pydantic import BaseModel

from app.db.rows import ChapterRow, Modality
from app.ingestion.blocks import Block
from app.ingestion.chapters import chapter_for_page

_CHARS_PER_TOKEN = 4


class ChunkDraft(BaseModel):
    """A chunk before contextualization/embedding."""

    content: str
    page: int
    bbox: dict[str, Any] | None = None  # bbox of the first contributing block
    modality: Modality = "text"
    chapter_ordinal: int | None = None
    image_bytes: bytes | None = None  # figure chunks, until captioned
    image_mime: str = "image/png"

    @property
    def token_count(self) -> int:
        return max(1, len(self.content) // _CHARS_PER_TOKEN)


def _split_text(text: str, size_tokens: int, overlap_tokens: int) -> list[str]:
    """Recursive character splitting: paragraphs → sentences → hard cut."""
    size, overlap = size_tokens * _CHARS_PER_TOKEN, overlap_tokens * _CHARS_PER_TOKEN
    if len(text) <= size:
        return [text]
    # try paragraph, then sentence boundaries within the window
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind(". "))
            if cut > size // 2:  # only take a boundary in the back half
                end = start + cut + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in parts if p]


def chunk_blocks(
    blocks: list[Block],
    chapters: list[ChapterRow],
    chunk_size_tokens: int = 800,
    chunk_overlap_tokens: int = 120,
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    # group consecutive text blocks per chapter so splits can cross block
    # boundaries but never chapter boundaries
    run_text: list[str] = []
    run_page, run_bbox, run_ord = 1, None, None

    def flush() -> None:
        nonlocal run_text, run_bbox
        if not run_text:
            return
        for piece in _split_text(
            "\n\n".join(run_text), chunk_size_tokens, chunk_overlap_tokens
        ):
            drafts.append(ChunkDraft(
                content=piece, page=run_page, bbox=run_bbox,
                modality="text", chapter_ordinal=run_ord,
            ))
        run_text, run_bbox = [], None

    for block in blocks:
        ch = chapter_for_page(chapters, block.page)
        ordinal = ch.ordinal if ch else None
        if block.block_type in ("heading-1", "heading-2"):
            flush()
            run_page, run_ord = block.page, ordinal
            continue
        if block.block_type == "list-item":
            continue  # structural-noise filter
        if block.block_type == "table":
            flush()
            drafts.append(ChunkDraft(
                content=block.text, page=block.page, bbox=block.bbox,
                modality="table", chapter_ordinal=ordinal,
            ))
            continue
        if block.block_type == "figure":
            flush()
            drafts.append(ChunkDraft(
                content=block.text,  # placeholder; captioner fills it
                page=block.page, bbox=block.bbox,
                modality="figure", chapter_ordinal=ordinal,
                image_bytes=block.image_bytes, image_mime=block.image_mime,
            ))
            continue
        if block.block_type == "caption":
            continue  # figure captions ride with their figure block
        # text block
        if ordinal != run_ord:
            flush()  # chapter boundary — never split across it
            run_ord = ordinal
        if not run_text:
            run_page, run_bbox = block.page, block.bbox
        run_text.append(block.text)
    flush()
    return drafts
