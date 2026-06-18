"""Eval metrics — keyword score and citation accuracy.

Deliberately minimal for the v1 mock-mode harness. RAGAS faithfulness /
answer-relevance are deferred to Phase 1 with a real generator, since they
require LLM-judge calls and are uninformative against the mock generator's
templated responses.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KeywordResult:
    score: float                # matches / len(keywords)
    matched: list[str]
    missed: list[str]


def keyword_score(answer: str, expected_keywords: list[str]) -> KeywordResult:
    """Substring + AND match. See learnings/05-keyword-set-design.md.

    Both the answer and keywords are lowercased before matching, per
    Convention C6 in eval/golden/README.md.
    """
    if not expected_keywords:
        return KeywordResult(score=1.0, matched=[], missed=[])
    answer_lc = answer.lower()
    matched, missed = [], []
    for kw in expected_keywords:
        if kw.lower() in answer_lc:
            matched.append(kw)
        else:
            missed.append(kw)
    return KeywordResult(
        score=len(matched) / len(expected_keywords),
        matched=matched,
        missed=missed,
    )


@dataclass
class CitationResult:
    score: float                # fraction of returned citations whose page falls in any expected_page_range
    in_range: int               # count of citations within expected ranges
    out_of_range: int
    book_match: bool            # at least one citation's book_id is in expected_books


def citation_accuracy(
    citations: list[dict],
    expected_books: list[str],
    expected_page_ranges: list[list[int]],
) -> CitationResult:
    """For each returned citation, check whether (book_id, page) lands inside
    any of the expected ranges. This is the project-specific metric flagged
    in technical-design.md as critical for NotebookLM-style citation UX.

    `citations` is the parsed `citations` SSE event payload (list of dicts
    with `bookId`, `page` keys, camelCase from the API).
    """
    if not citations:
        return CitationResult(score=0.0, in_range=0, out_of_range=0, book_match=False)

    in_range = 0
    out_of_range = 0
    book_match = False
    for c in citations:
        book_id = c.get("bookId") or c.get("book_id")
        page = c.get("page")
        if book_id in expected_books:
            book_match = True
        # A citation is "in range" if its book is expected AND page falls in
        # any of the expected ranges for that book.
        hit = False
        for exp_book, (lo, hi) in zip(expected_books, expected_page_ranges):
            if book_id == exp_book and lo <= page <= hi:
                hit = True
                break
        if hit:
            in_range += 1
        else:
            out_of_range += 1

    total = in_range + out_of_range
    return CitationResult(
        score=in_range / total if total else 0.0,
        in_range=in_range,
        out_of_range=out_of_range,
        book_match=book_match,
    )
