"""M3 unit tests — fixtures + fakes only, zero paid API calls, zero DB."""

import math

import pytest

from app.core.config import Settings
from app.db.rows import BookRow
from app.ingestion.blocks import Block
from app.ingestion.chapters import chapter_for_page, detect_chapters
from app.ingestion.chunker import chunk_blocks
from app.ingestion.embedder import Embedder, l2_normalize
from app.ingestion.pipeline import IngestionPipeline, build_chapter_texts


def _blocks() -> list[Block]:
    """Two chapters; ch.1 has enough prose to force a split at size=100."""
    long_para = ("The solar nebula collapsed under gravity. " * 40).strip()
    return [
        Block(page=1, block_type="heading-1", text="Chapter 1: Origins"),
        Block(page=1, block_type="text", text=long_para),
        Block(page=2, block_type="text", text="Planetesimals accreted into planets."),
        Block(page=2, block_type="list-item", text="Key Terms: accretion, nebula"),
        Block(page=3, block_type="text",
              text="As we saw above, see Chapter 5 for orbital dynamics details in prose."),
        Block(page=4, block_type="heading-1", text="Chapter 2: The Moon"),
        Block(page=4, block_type="text", text="The Moon formed after a giant impact."),
        Block(page=4, block_type="table", text="| body | radius |\n| moon | 1737 km |"),
    ]


def test_detect_chapters_and_page_mapping():
    chapters = detect_chapters(_blocks(), "b1")
    assert [(c.ordinal, c.start_page, c.end_page) for c in chapters] == [
        (1, 1, 3), (2, 4, None),
    ]
    assert chapter_for_page(chapters, 3).ordinal == 1
    assert chapter_for_page(chapters, 9).ordinal == 2
    # "see Chapter 5" prose (page 3, text block, 12+ words) must NOT be a chapter
    assert all(c.ordinal != 5 for c in chapters)


def test_chunker_respects_chapters_and_filters_noise():
    chapters = detect_chapters(_blocks(), "b1")
    chunks = chunk_blocks(_blocks(), chapters, chunk_size_tokens=100, chunk_overlap_tokens=20)

    # list-item (Key Terms) filtered — the Phase 1 structural-noise fix
    assert not any("Key Terms" in c.content for c in chunks)
    # no chunk mixes chapters: content from ch.2 never appears with ch.1 ordinal
    for c in chunks:
        if "giant impact" in c.content:
            assert c.chapter_ordinal == 2
            assert "solar nebula" not in c.content.lower()
    # long paragraph split with overlap
    ch1_text = [c for c in chunks if c.chapter_ordinal == 1 and c.modality == "text"]
    assert len(ch1_text) >= 2
    # table became its own chunk
    assert any(c.modality == "table" for c in chunks)


def test_l2_normalize():
    v = l2_normalize([3.0, 4.0])
    assert v == pytest.approx([0.6, 0.8])
    assert math.isclose(sum(x * x for x in l2_normalize([0.1] * 768)), 1.0)
    assert l2_normalize([0.0, 0.0]) == [0.0, 0.0]  # zero vector: no div-by-zero


class _FakeEmbedClient:
    """Returns constant unnormalized vectors; counts API calls."""

    def __init__(self) -> None:
        self.calls = 0
        outer = self

        class _Models:
            async def embed_content(self, **kwargs):
                outer.calls += 1
                n = len(kwargs["contents"])

                class E:
                    values = (1.0, 1.0, 1.0, 1.0)

                class R:
                    embeddings = [E()] * n

                return R()

        class _Aio:
            models = _Models()

        self.aio = _Aio()


async def test_embedder_normalizes_and_caches(tmp_path):
    settings = Settings(ingest_cache_dir=str(tmp_path), embedding_dim=4)
    fake = _FakeEmbedClient()
    embedder = Embedder(settings, client=fake)  # type: ignore[arg-type]

    out1 = await embedder.embed(["alpha", "beta"])
    assert fake.calls == 1
    assert all(math.isclose(sum(x * x for x in v), 1.0) for v in out1)

    out2 = await embedder.embed(["alpha", "beta"])  # cache hit — no new call
    assert fake.calls == 1
    assert out1 == out2


class _FakeContextualizer:
    async def contextualize(self, chunk_text: str, chapter_text: str) -> str:
        assert chapter_text  # pipeline must pass the parent chapter
        return "From Chapter 1, on the origin of the solar system."


class _FakeEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        # pipeline must embed the CONTEXTUALIZED text, not bare content
        assert all(t.startswith("From Chapter") or "Moon" in t or "|" in t for t in texts)
        return [[0.5] * 4 for _ in texts]


async def test_pipeline_build_chunks_wires_prefix_into_embedding():
    settings = Settings(chunk_size_tokens=100, chunk_overlap_tokens=20)
    pipe = IngestionPipeline(
        settings,
        contextualizer=_FakeContextualizer(),  # type: ignore[arg-type]
        embedder=_FakeEmbedder(),  # type: ignore[arg-type]
    )
    book = BookRow(book_id="b1", title="T", author="A", gcs_uri="gs://x")
    chapters, rows = await pipe.build_chunks(_blocks(), book)

    assert len(chapters) == 2
    assert rows and all(r.embedding == [0.5] * 4 for r in rows)
    ch1_rows = [r for r in rows if r.context_prefix]
    assert ch1_rows and all(
        r.context_prefix.startswith("From Chapter") for r in ch1_rows
    )
    # verbatim content NEVER contains the prefix — display/citation property
    assert all(
        r.context_prefix not in r.content for r in ch1_rows
    )


def test_chapters_from_toc(tmp_path):
    import fitz

    from app.ingestion.chapters import chapters_from_toc

    pdf = tmp_path / "toy.pdf"
    doc = fitz.open()
    for _ in range(6):
        doc.new_page()
    doc.set_toc([
        [1, "Preface", 1],
        [1, "Chapter 1 Origins", 2],
        [2, "1.1 The Nebula", 2],
        [1, "Chapter 2 The Moon", 4],
        [1, "Appendix A Units", 6],
    ])
    doc.save(str(pdf))

    chapters = chapters_from_toc(str(pdf), "b1")
    assert [(c.ordinal, c.start_page, c.end_page) for c in chapters] == [
        (1, 2, 3), (2, 4, 5), (1000, 6, None),
    ]
    assert chapters[0].title == "Chapter 1 Origins"  # Preface + 1.1 excluded


def _hit(i: int):
    from app.db.rows import SearchHit

    return SearchHit(
        chunk_id=i, book_id="b", book_title="T", author="A",
        page=1, content=f"passage {i}", rrf_score=1.0 / i,
    )


class _FakeRerankClient:
    def __init__(self, text: str) -> None:
        outer_text = text

        class _Models:
            async def generate_content(self, **kwargs):
                class R:
                    text = outer_text

                return R()

        class _Aio:
            models = _Models()

        self.aio = _Aio()


async def test_reranker_orders_by_scores():
    from app.services.retrieval.reranker import GeminiReranker

    settings = Settings()
    rr = GeminiReranker(settings, client=_FakeRerankClient("[1, 9, 5]"))  # type: ignore[arg-type]
    out = await rr.rerank("q", [_hit(1), _hit(2), _hit(3)], keep=2)
    assert [h.chunk_id for h in out] == [2, 3]  # scores 9, 5


async def test_reranker_falls_back_to_rrf_on_bad_json():
    from app.services.retrieval.reranker import GeminiReranker

    settings = Settings()
    rr = GeminiReranker(settings, client=_FakeRerankClient("not json"))  # type: ignore[arg-type]
    out = await rr.rerank("q", [_hit(1), _hit(2), _hit(3)], keep=2)
    assert [h.chunk_id for h in out] == [1, 2]  # RRF order preserved


def test_part_for_ordinal_contract():
    from app.ingestion.parts import ASTRO_PARTS, part_for_ordinal

    assert part_for_ordinal(None) == "openstax-astronomy-2e-pt1"   # front matter
    assert part_for_ordinal(1) == "openstax-astronomy-2e-pt1"
    assert part_for_ordinal(6) == "openstax-astronomy-2e-pt1"
    assert part_for_ordinal(7) == "openstax-astronomy-2e-pt2"
    assert part_for_ordinal(24) == "openstax-astronomy-2e-pt3"
    assert part_for_ordinal(30) == "openstax-astronomy-2e-pt4"
    assert part_for_ordinal(1000) == "openstax-astronomy-2e-pt4"   # appendix A
    # ids must match the locked golden convention exactly
    assert [p[0] for p in ASTRO_PARTS] == [
        f"openstax-astronomy-2e-pt{n}" for n in (1, 2, 3, 4)
    ]


def test_build_chapter_texts_groups_by_ordinal():
    blocks = _blocks()
    chapters = detect_chapters(blocks, "b1")
    texts = build_chapter_texts(blocks, chapters)
    assert "solar nebula" in texts[1].lower()
    assert "giant impact" in texts[2].lower()
    assert "giant impact" not in texts[1].lower()
