"""Static fixture retriever — lets the frontend be developed without any GCP access.

Content sampled from OpenStax *Astronomy 2e* (Fraknoi, Morrison, Wolff; Rice University,
2026), licensed CC BY-NC-SA 4.0. Access for free at openstax.org/details/books/astronomy-2e.
"""

from app.models.book import Book
from app.models.citation import BoundingBox, RetrievedChunk
from app.services.retrieval.base import Retriever

_OPENSTAX_AUTHORS = "Fraknoi, Morrison & Wolff (OpenStax)"

_BOOKS: list[Book] = [
    Book(
        book_id="openstax-astronomy-2e-pt1",
        title="Astronomy 2e — Part I: Foundations & Methods (Ch. 1–6)",
        author=_OPENSTAX_AUTHORS,
        year=2026,
        page_count=220,
        gcs_uri="gs://example/openstax/astronomy-2e/part1.pdf",
    ),
    Book(
        book_id="openstax-astronomy-2e-pt2",
        title="Astronomy 2e — Part II: The Solar System (Ch. 7–14)",
        author=_OPENSTAX_AUTHORS,
        year=2026,
        page_count=300,
        gcs_uri="gs://example/openstax/astronomy-2e/part2.pdf",
    ),
    Book(
        book_id="openstax-astronomy-2e-pt3",
        title="Astronomy 2e — Part III: Stars & Stellar Evolution (Ch. 15–24)",
        author=_OPENSTAX_AUTHORS,
        year=2026,
        page_count=320,
        gcs_uri="gs://example/openstax/astronomy-2e/part3.pdf",
    ),
    Book(
        book_id="openstax-astronomy-2e-pt4",
        title="Astronomy 2e — Part IV: Galaxies, Cosmology & Life (Ch. 25–30)",
        author=_OPENSTAX_AUTHORS,
        year=2026,
        page_count=270,
        gcs_uri="gs://example/openstax/astronomy-2e/part4.pdf",
    ),
]


_FIXTURE_CHUNKS: list[RetrievedChunk] = [
    RetrievedChunk(
        chunk_id="astronomy-2e-ch3-p70",
        book_id="openstax-astronomy-2e-pt1",
        book_title="Astronomy 2e — Part I",
        author=_OPENSTAX_AUTHORS,
        chapter_num=3,
        chapter_title="Orbits and Gravity",
        page=70,
        content=(
            "Through his analysis of the motions of the planets, Kepler developed a series "
            "of principles, now known as Kepler's three laws, which described the behavior "
            "of planets based on their paths through space. The first two laws of planetary "
            "motion were published in 1609 in The New Astronomy. Working with the data for "
            "Mars, he eventually discovered that the orbit of that planet had the shape of "
            "a somewhat flattened circle, or ellipse."
        ),
        score=0.93,
        bbox=BoundingBox(x0=110, y0=220, x1=500, y1=380),
    ),
    RetrievedChunk(
        chunk_id="astronomy-2e-ch15-p522",
        book_id="openstax-astronomy-2e-pt3",
        book_title="Astronomy 2e — Part III",
        author=_OPENSTAX_AUTHORS,
        chapter_num=15,
        chapter_title="The Sun: A Garden-Variety Star",
        page=522,
        content=(
            "What we now study as space weather was first recognized — though not yet "
            "understood — in 1859, in what is now known as the Carrington Event. In early "
            "September of that year, two amateur astronomers, including Richard Carrington "
            "in England, independently observed a solar flare. This was followed a day or "
            "two later by a significant solar storm reaching the region of Earth's magnetic "
            "field. Aurora activity was intense and the northern lights were visible as far "
            "south as Hawaii and the Caribbean. Sparks were seen coming out of exposed "
            "wires and telegraph machines."
        ),
        score=0.89,
    ),
    RetrievedChunk(
        chunk_id="astronomy-2e-ch26-p902",
        book_id="openstax-astronomy-2e-pt4",
        book_title="Astronomy 2e — Part IV",
        author=_OPENSTAX_AUTHORS,
        chapter_num=26,
        chapter_title="Galaxies",
        page=902,
        content=(
            "Beginning in 1912, and making heroic efforts over a period of about 20 years, "
            "Slipher managed to photograph the spectra of more than 40 of the spiral nebulae. "
            "To his surprise, the spectral lines of most galaxies showed an astounding "
            "redshift — the lines in the spectra are displaced toward longer wavelengths. "
            "Slipher's observations showed that most spirals are racing away at huge speeds; "
            "the highest velocity he measured was 1800 kilometers per second. Only a few "
            "spirals — Andromeda, Triangulum, and M81 — turned out to be approaching us."
        ),
        score=0.74,
    ),
]


class MockRetriever(Retriever):
    async def list_books(self) -> list[Book]:
        return list(_BOOKS)

    async def retrieve(
        self,
        query: str,
        top_k: int,
        book_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        chunks = _FIXTURE_CHUNKS
        if book_ids:
            chunks = [c for c in chunks if c.book_id in book_ids]
        return chunks[:top_k]
