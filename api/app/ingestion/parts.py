"""Canonical 4-part split for OpenStax Astronomy 2e.

book_ids are the golden-set contract (eval/golden/README.md C-rules) —
learnings/11 story 7 is what happens when ingestion invents its own ids.
Front matter (no chapter) → pt1; appendices (ordinal >= 1000) → pt4.
"""

from app.db.rows import BookRow

ASTRO_PARTS: list[tuple[str, str, int, int]] = [
    ("openstax-astronomy-2e-pt1", "Astronomy 2e — Part I: Foundations & Methods", 1, 6),
    ("openstax-astronomy-2e-pt2", "Astronomy 2e — Part II: Solar System", 7, 14),
    ("openstax-astronomy-2e-pt3", "Astronomy 2e — Part III: Stars & Stellar Evolution", 15, 24),
    ("openstax-astronomy-2e-pt4", "Astronomy 2e — Part IV: Galaxies, Cosmology & Life", 25, 30),
]

_AUTHOR = "Fraknoi, Morrison, Wolff"


def part_for_ordinal(ordinal: int | None) -> str:
    if ordinal is None:
        return ASTRO_PARTS[0][0]  # front matter → pt1
    if ordinal >= 1000:
        return ASTRO_PARTS[-1][0]  # appendices → pt4
    for book_id, _, lo, hi in ASTRO_PARTS:
        if lo <= ordinal <= hi:
            return book_id
    return ASTRO_PARTS[-1][0]


def part_books(gcs_uri: str, year: int | None = 2026) -> list[BookRow]:
    return [
        BookRow(book_id=bid, title=title, author=_AUTHOR, year=year,
                gcs_uri=gcs_uri, source="openstax")
        for bid, title, _, _ in ASTRO_PARTS
    ]
