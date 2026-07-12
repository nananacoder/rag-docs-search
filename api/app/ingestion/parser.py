"""PDF → layout blocks (§4.1).

Primary: Document AI Layout Parser (typed blocks + bbox — required for the
structural-noise filter and bbox citations). Fallback: pymupdf text-only
extraction with a logged warning (rare: corrupted PDFs, quota).

The pymupdf path doubles as the free local/test parser.
"""

import re
from typing import Any, ClassVar

import fitz  # pymupdf

from app.core.logging import get_logger
from app.ingestion.blocks import Block

log = get_logger(__name__)

# Body text below this share of page height is usually a running footer.
_FOOTER_ZONE = 0.94


class PymupdfParser:
    """Text-only fallback parser. Emits text/heading blocks with bbox.

    Heading detection: pymupdf spans carry font size; blocks whose max font
    size clears the page's body-size estimate by >40% become heading-1,
    >15% heading-2. Crude, but only the fallback path — Document AI's typed
    layout is the primary source of heading signals.
    """

    def parse(self, pdf_path: str) -> list[Block]:
        blocks: list[Block] = []
        with fitz.open(pdf_path) as doc:
            for page_no, page in enumerate(doc, start=1):
                w, h = page.rect.width or 1.0, page.rect.height or 1.0
                body_size = self._body_font_size(page)
                for b in page.get_text("dict")["blocks"]:
                    if b.get("type") != 0:  # 0 = text block
                        continue
                    text = " ".join(
                        s["text"] for line in b["lines"] for s in line["spans"]
                    ).strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = b["bbox"]
                    if y0 / h > _FOOTER_ZONE:
                        continue  # running footer / page number
                    max_size = max(
                        (s["size"] for line in b["lines"] for s in line["spans"]),
                        default=body_size,
                    )
                    btype = "text"
                    if max_size > body_size * 1.4:
                        btype = "heading-1"
                    elif max_size > body_size * 1.15:
                        btype = "heading-2"
                    blocks.append(Block(
                        page=page_no,
                        bbox={"x0": x0 / w, "y0": y0 / h, "x1": x1 / w, "y1": y1 / h},
                        block_type=btype,
                        text=re.sub(r"\s+", " ", text),
                    ))
        log.info("pymupdf_parsed", blocks=len(blocks))
        return blocks

    @staticmethod
    def _body_font_size(page: fitz.Page) -> float:
        sizes = [
            s["size"]
            for b in page.get_text("dict")["blocks"]
            if b.get("type") == 0
            for line in b["lines"]
            for s in line["spans"]
        ]
        if not sizes:
            return 10.0
        sizes.sort()
        return float(sizes[len(sizes) // 2])  # median


class DocumentAIParser:
    """Document AI Layout Parser via batch processing (1,151 pages >> the
    ~15-page online limit). Requires DOCAI_PROCESSOR_NAME and
    DOCAI_GCS_OUTPUT_PREFIX. Exercised only in the paid ingestion run —
    the free pipeline path and all tests use PymupdfParser.
    """

    # Document AI layoutType → our BlockType
    _TYPE_MAP: ClassVar[dict[str, str]] = {
        "paragraph": "text",
        "table": "table",
        "figure": "figure",
        "heading-1": "heading-1",
        "heading-2": "heading-2",
        "heading-3": "heading-2",
        "list-item": "list-item",
        "caption": "caption",
    }

    def __init__(self, processor_name: str, gcs_output_prefix: str) -> None:
        self.processor_name = processor_name
        self.gcs_output_prefix = gcs_output_prefix

    def parse_gcs(self, gcs_uri: str) -> list[Block]:
        """Batch-process a GCS PDF; poll until done; map result JSON to Blocks."""
        from google.cloud import documentai

        client = documentai.DocumentProcessorServiceClient()
        request = documentai.BatchProcessRequest(
            name=self.processor_name,
            input_documents=documentai.BatchDocumentsInputConfig(
                gcs_documents=documentai.GcsDocuments(
                    documents=[documentai.GcsDocument(
                        gcs_uri=gcs_uri, mime_type="application/pdf"
                    )]
                )
            ),
            document_output_config=documentai.DocumentOutputConfig(
                gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                    gcs_uri=self.gcs_output_prefix
                )
            ),
        )
        operation = client.batch_process_documents(request)
        log.info("docai_batch_started", operation=operation.operation.name)
        # Layout parsing 1,151 pages can take a while
        operation.result(timeout=3600)  # type: ignore[no-untyped-call]
        return self._collect_output()

    def _collect_output(self) -> list[Block]:
        """Read batch output JSON shards from GCS and flatten to Blocks."""
        from google.cloud import documentai, storage  # type: ignore[attr-defined]

        bucket_name, _, prefix = self.gcs_output_prefix.removeprefix("gs://").partition("/")
        blocks: list[Block] = []
        for blob in storage.Client().list_blobs(bucket_name, prefix=prefix):
            if not blob.name.endswith(".json"):
                continue
            doc = documentai.Document.from_json(
                blob.download_as_bytes(), ignore_unknown_fields=True
            )
            blocks.extend(self._document_to_blocks(doc))
        log.info("docai_parsed", blocks=len(blocks))
        return blocks

    def _document_to_blocks(self, doc: Any) -> list[Block]:
        """Map a Document AI layout document to Blocks.

        NOTE: field paths verified against google-cloud-documentai at the
        paid-run stage; the layout schema (documentLayout.blocks with
        textBlock.type_/text and pageSpan) is the June 2026 shape.
        """
        blocks: list[Block] = []
        layout = getattr(doc, "document_layout", None)
        if layout is None:
            return blocks
        for b in layout.blocks:
            tb = getattr(b, "text_block", None)
            if tb is None:
                continue
            btype = self._TYPE_MAP.get(str(tb.type_), "text")
            page = int(b.page_span.page_start) if b.page_span else 1
            bbox = None
            if getattr(b, "bounding_box", None):
                vs = b.bounding_box.normalized_vertices
                if len(vs) >= 3:
                    bbox = {"x0": vs[0].x, "y0": vs[0].y, "x1": vs[2].x, "y1": vs[2].y}
            blocks.append(Block(
                page=page,
                bbox=bbox,
                block_type=btype,
                text=tb.text or "",
            ))
        return blocks
