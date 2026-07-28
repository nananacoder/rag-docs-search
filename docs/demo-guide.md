# Interview Demo Guide — near-zero-cost live walkthrough

Current cloud footprint after teardown (2026-07-28): **Cloud SQL deleted**
(it was the only daily cost). Kept, all ~¥0/month: the corpus PDF in GCS
(`my-rag-docs-bucket-123`) and the Phase 1 Vertex AI Search datastore.
Everything below runs **free** (mock backend; only a few cents of GCS
egress when the PDF streams).

## The 3-minute live demo (free)

**Setup** (two terminals):
```bash
# Terminal 1 — API in mock mode (no Cloud SQL, no cost; needs GCP ADC for the PDF)
cd api && RETRIEVAL_BACKEND=mock poetry run uvicorn app.main:app --port 8000

# Terminal 2 — Angular UI
cd web && npm start        # http://localhost:4200
```

**Flow to show:**
1. Ask a question (e.g. *"What did Slipher observe about spiral nebulae?"*).
   The answer streams in with inline `[1] [2]` citations.
2. **Click a citation** → the right pane loads the real PDF page (streamed
   from GCS) and **draws a highlight box on the exact source text**.
3. That highlight is the headline: *"Phase 1's managed search returned no
   page and no bbox — every citation pointed at page 1. Phase 2's own
   ingestion gives per-chunk (page, bbox), so I can point at the sentence."*

> Mock returns 3 fixture citations with **real normalized bbox** — the
> overlay math is the same code path as production. You're demoing the real
> UX; only the retrieval source is stubbed.

## What to say about each phase (since Phase 2 retrieval is now offline)

Phase 2's live pgvector retrieval needs Cloud SQL, which is deleted to save
cost. You demo it from the **measured artifacts**, not a live query:

- **The A/B result** — `docs/phase2-ab-report.md`: keyword 18.5%→86.5%,
  citation 0%→57.5%, cross_topic & figure buckets 0%→100%. *"Same corpus,
  same generator, same eval — only retrieval changed."*
- **The run cards** — `eval/runs/`: the actual per-question scores.
- **The design + decisions** — `phase2-selfbuilt.md`, `docs/adr/*` (8 ADRs),
  `learnings/11` (9 implementation war stories).

If you need Phase 2 **live** for a specific interview, rebuild it (~20 min,
~¥1): `sql-start.sh` a fresh instance, apply `schema.sql`, re-run
`python -m app.ingestion.pipeline --pdf … --split-astro-parts` (ingestion
caches make the LLM calls free), then `RETRIEVAL_BACKEND=pgvector`. Tear
down with `sql-stop.sh`/delete after. **Note**: Cloud SQL's port 3307 is
firewall-blocked on some networks (learnings/11 §9) — test the connection
before relying on it for a live demo.

## The strongest 60-second pitch

> *"Two RAG architectures on the same corpus, generator, and eval — I
> measured what you give up going managed, then what you get back going
> self-built. Keyword accuracy 18.5%→86.5%, citations 0%→57.5%, and each
> gain maps to a specific failure I measured in Phase 1. The whole
> two-system experiment cost about $12 — because I treated cost as an
> engineering metric: scale-to-zero, cached paid stages, and I replaced a
> $11.5 Document AI step with a $1 substitute after measuring it didn't
> move my retrieval numbers."*

## Talking points that land (each has a doc/story behind it)

- **"I read what was broken, then designed each fix."** Every Phase 2 choice
  maps to a measured Phase 1 zero-bucket.
- **"I dropped SQLAlchemy, LangChain, and RAGAS-the-library — each time the
  framework fought the platform harder than the problem did."** (ADR-003,
  learnings/11 §8). Judgment, not framework-collecting.
- **"Real data broke my design assumption."** Chapter regex found 0 chapters
  on the real PDF; the bookmark outline found 43/43 (learnings/11 §1).
- **"Cost pressure is a legitimate engineering input."** The teardown
  decisions (Document AI substitution, session-based DB, final delete).
