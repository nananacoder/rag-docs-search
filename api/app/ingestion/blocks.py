"""Layout block model — the unit flowing from parser to chunker (§4.1)."""

from typing import Any, Literal

from pydantic import BaseModel

BlockType = Literal[
    "text", "table", "figure", "heading-1", "heading-2", "list-item", "caption"
]


class Block(BaseModel):
    """One layout block from Document AI (or the pymupdf fallback)."""

    page: int  # 1-indexed PDF page
    bbox: dict[str, Any] | None = None  # {x0,y0,x1,y1}, normalized 0-1
    block_type: BlockType = "text"
    text: str = ""
    image_bytes: bytes | None = None  # figure blocks only
