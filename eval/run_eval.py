"""Eval harness — runs the golden set against the live API and produces a
markdown run card.

Usage:
    poetry run python eval/run_eval.py \
        --golden eval/golden/v1.jsonl \
        --api http://localhost:8000 \
        --out eval/runs/phase1-mock-v1.md

Calls the running FastAPI service over HTTP, parses the SSE stream, and
scores each entry. Mock mode (default API config) produces meaningful
keyword + citation scores against templated answers; real Phase 1 mode
adds informative scores once the API is pointed at Vertex AI Search.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import httpx

# Allow running as a script from project root: python eval/run_eval.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import CitationResult, KeywordResult, citation_accuracy, keyword_score  # noqa: E402


@dataclass
class GoldenEntry:
    qid: str
    question: str
    expected_answer_keywords: list[str]
    expected_books: list[str]
    expected_chapters: list[str]
    expected_page_ranges: list[list[int]]
    query_type: str
    notes: str


@dataclass
class QueryResult:
    citations: list[dict]
    answer: str
    total_ms: int | None
    model: str | None
    error: str | None = None


@dataclass
class ScoredEntry:
    entry: GoldenEntry
    result: QueryResult
    keyword: KeywordResult
    citation: CitationResult


def load_golden(path: Path) -> list[GoldenEntry]:
    entries = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            entries.append(GoldenEntry(**{k: obj[k] for k in GoldenEntry.__annotations__}))
    return entries


def call_api(api_base: str, question: str, book_ids: list[str] | None = None) -> QueryResult:
    """POST /api/query and consume the SSE stream until the 'done' event.

    Returns a QueryResult with the assembled answer and metadata.
    """
    url = f"{api_base.rstrip('/')}/api/query"
    payload = {"question": question}
    if book_ids:
        payload["bookIds"] = book_ids

    citations: list[dict] = []
    tokens: list[str] = []
    total_ms = None
    model = None
    error = None

    try:
        with httpx.Client(timeout=120.0) as client:
            with client.stream("POST", url, json=payload) as r:
                r.raise_for_status()
                for raw_line in r.iter_lines():
                    if not raw_line or not raw_line.startswith("data:"):
                        continue
                    data_str = raw_line[len("data:"):].strip()
                    if not data_str:
                        continue
                    try:
                        evt = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    etype = evt.get("type")
                    if etype == "citations":
                        citations = evt.get("citations", [])
                    elif etype == "token":
                        tokens.append(evt.get("text", ""))
                    elif etype == "done":
                        total_ms = evt.get("totalMs") or evt.get("total_ms")
                        model = evt.get("model")
                    elif etype == "error":
                        error = evt.get("message")
    except httpx.HTTPError as exc:
        error = f"HTTP error: {exc}"

    return QueryResult(
        citations=citations,
        answer="".join(tokens),
        total_ms=total_ms,
        model=model,
        error=error,
    )


def score_entry(entry: GoldenEntry, result: QueryResult) -> ScoredEntry:
    kw = keyword_score(result.answer, entry.expected_answer_keywords)
    cite = citation_accuracy(
        citations=result.citations,
        expected_books=entry.expected_books,
        expected_page_ranges=entry.expected_page_ranges,
    )
    return ScoredEntry(entry=entry, result=result, keyword=kw, citation=cite)


def render_markdown(scored: list[ScoredEntry], api_base: str, golden_path: Path) -> str:
    """Produce a run card. Sections: header, overall, per-bucket, per-question."""
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")

    # Overall
    n = len(scored)
    avg_kw = statistics.mean(s.keyword.score for s in scored) if n else 0
    avg_cite = statistics.mean(s.citation.score for s in scored) if n else 0
    n_errors = sum(1 for s in scored if s.result.error)
    avg_latency = statistics.mean(
        s.result.total_ms for s in scored if s.result.total_ms is not None
    ) if any(s.result.total_ms for s in scored) else None
    model = next((s.result.model for s in scored if s.result.model), "unknown")

    # Per-bucket
    by_bucket: dict[str, list[ScoredEntry]] = defaultdict(list)
    for s in scored:
        by_bucket[s.entry.query_type].append(s)

    lines: list[str] = []
    lines.append(f"# Eval Run Card — {golden_path.name}")
    lines.append("")
    lines.append(f"- **Run timestamp (UTC):** {now}")
    lines.append(f"- **API base:** `{api_base}`")
    lines.append(f"- **Model reported by API:** `{model}`")
    lines.append(f"- **Golden set:** `{golden_path}`")
    lines.append(f"- **Questions:** {n}")
    lines.append(f"- **Errors:** {n_errors}")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Avg keyword score | **{avg_kw:.2%}** |")
    lines.append(f"| Avg citation accuracy | **{avg_cite:.2%}** |")
    if avg_latency is not None:
        lines.append(f"| Avg latency (ms) | {avg_latency:.0f} |")
    lines.append("")

    lines.append("## Per-bucket")
    lines.append("")
    lines.append("| Bucket | N | Keyword | Citation |")
    lines.append("|---|---|---|---|")
    for bucket in ["factual", "chapter_scoped", "cross_topic", "figure_or_diagram"]:
        items = by_bucket.get(bucket, [])
        if not items:
            lines.append(f"| {bucket} | 0 | — | — |")
            continue
        kw = statistics.mean(i.keyword.score for i in items)
        ct = statistics.mean(i.citation.score for i in items)
        lines.append(f"| {bucket} | {len(items)} | {kw:.2%} | {ct:.2%} |")
    lines.append("")

    lines.append("## Per-question detail")
    lines.append("")
    for s in scored:
        lines.append(f"### {s.entry.qid} — `{s.entry.query_type}`")
        lines.append("")
        lines.append(f"**Q:** {s.entry.question}")
        lines.append("")
        if s.result.error:
            lines.append(f"⚠️ **Error:** {s.result.error}")
            lines.append("")
            continue
        lines.append(f"- Keyword score: **{s.keyword.score:.2%}** "
                     f"(matched: {s.keyword.matched}; missed: {s.keyword.missed})")
        lines.append(f"- Citation: **{s.citation.score:.2%}** "
                     f"(in_range={s.citation.in_range}, out_of_range={s.citation.out_of_range}, "
                     f"book_match={s.citation.book_match})")
        if s.result.total_ms is not None:
            lines.append(f"- Latency: {s.result.total_ms} ms")
        ans = s.result.answer.strip().replace("\n", " ")
        if len(ans) > 400:
            ans = ans[:397] + "…"
        lines.append("")
        lines.append(f"> {ans}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--golden", type=Path, default=Path("eval/golden/v1.jsonl"))
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--out", type=Path, default=None,
                   help="Markdown output path. Default: eval/runs/run-<timestamp>.md")
    p.add_argument("--scope-books", action="store_true",
                   help="Pass each golden entry's expected_books as the bookIds filter "
                        "(simulates UI-scoped queries instead of unscoped).")
    args = p.parse_args()

    if not args.golden.exists():
        print(f"Golden set not found: {args.golden}", file=sys.stderr)
        return 1

    entries = load_golden(args.golden)
    print(f"Loaded {len(entries)} golden entries from {args.golden}")

    scored: list[ScoredEntry] = []
    for i, entry in enumerate(entries, 1):
        print(f"[{i}/{len(entries)}] {entry.qid}: {entry.question[:70]}…")
        t0 = time.monotonic()
        result = call_api(
            args.api,
            entry.question,
            book_ids=entry.expected_books if args.scope_books else None,
        )
        dt_ms = int((time.monotonic() - t0) * 1000)
        if result.error:
            print(f"  ⚠️  {result.error}")
        else:
            print(f"  done in {dt_ms} ms — kw matches: {len(entry.expected_answer_keywords)} expected")
        scored.append(score_entry(entry, result))

    if args.out is None:
        ts = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        args.out = Path(f"eval/runs/run-{ts}.md")
    args.out.parent.mkdir(parents=True, exist_ok=True)

    md = render_markdown(scored, args.api, args.golden)
    args.out.write_text(md)
    print(f"\nRun card written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
