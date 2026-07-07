# Session Handoff — Phase 2 Design Locked

**Session date range**: ~2026-05-20 to 2026-07-07
**Handoff purpose**: Continue Phase 2 on a different device / new Claude Code session.

This is a **handoff note** — the process record, not the deliverables.
The deliverables are the formal docs (`interview-guide.md`,
`phase2-selfbuilt.md`, `learnings/*`). This note captures the decision
context that isn't otherwise obvious from the docs.

---

## Where the project actually stands

**Branch**: `stage2-pgvector` (pushed to origin)
**HEAD**: `ebc66bb` — "phase2: switch DB layer from SQLAlchemy ORM to Pydantic + Repository"

**Phase 1**: fully deployed on GCP. Vertex AI Search datastore
`astronomy-2e-datastore` in project `multimodal-rag-engine`. Baseline
measured — 8-question golden set, 18.5% keyword score after prompt
tuning, 0% citation accuracy (structural — Standard tier can't return
page numbers). Datastore still live; will serve as Phase 1 half of A/B.

**Phase 2**: design fully locked as of this session. Nothing implemented
yet. Next milestone is M2 (Cloud SQL schema + connection). See "What's
next" below.

**Costs so far**: < $5 USD total on GCP. Vertex AI Search idle is nearly
free. No Cloud SQL provisioned yet. Budget alert at ¥2000/month is
comfortable.

---

## Decisions that took real deliberation this session

These are locked in the formal docs but the *why* here is denser than
what those docs contain.

### 1. DB layer: Pydantic + Repository, NOT SQLAlchemy

Locked in `phase2-selfbuilt.md §2.5` and `interview-guide.md §11`.

The commit history shows the deliberation:
- `f800f0d` (initial): SQLAlchemy 2.x async, following the "GCP 2026
  recommended" pattern
- `ebc66bb` (reversal, hours later): Pydantic + Repository, no ORM

**What actually flipped the decision**: the user pointed out (correctly)
that Pydantic is already the project's data-modeling library and they
have prior industry experience wrapping ORM patterns manually. The
"SQLAlchemy is the GCP-recommended standard" argument was weaker than
"introduce a second modeling system just for DB layer" was expensive.

**The decisive engineering observation**: for our workload (hybrid
retrieval CTE + RRF fusion), we're writing raw SQL either way. ORM only
saves lines on `CREATE TABLE` and simple `INSERT`. That's not enough
value to justify the second modeling system.

**If you're the future engineer reading this**: don't second-guess this.
It was reasoned. If you're tempted to re-introduce SQLAlchemy, ask
first "does my new query benefit from ORM query builder specifically,
in a way raw SQL doesn't?" — usually no.

### 2. Schema: schema.sql + Cloud SQL Studio, NOT Alembic

Locked in `phase2-selfbuilt.md §2.5 → Schema management`.

Reasoning that isn't in the doc: **prior industry experience with
Alembic/Django-migrations lived in multi-developer projects with weekly
schema evolution**. This project is 1 developer, ~5 schema changes
total expected. Migration-framework operational cost isn't recouped.
If the project ever grows past those limits, revisit — the doc explicitly
says so.

The alternative I briefly considered — hand-writing a 30-line
`migrate.py` runner that tracks applied migrations — was rejected
because for our change cadence, even that runner is over-engineering.
Cloud SQL Studio + `IF NOT EXISTS` guards on schema.sql handles the
whole case.

### 3. Contextual Retrieval: adopt in M3 as core feature

Coming out of `learnings/10-phase2-design-audit-2026.md`. Not yet
integrated into `phase2-selfbuilt.md §4` — **that's an M3 task**.

**Key numbers to remember**: Anthropic reports 35% recall failure
reduction alone, 49% with contextual BM25, 67% stacked with rerank.
Cost at our scale is ~$3 USD one-time. This is the single
highest-leverage 2026 adoption. Do NOT skip it.

**Implementation shape**: for each chunk, before embedding and
BM25-indexing, call Gemini 2.5 Flash with the parent chapter as cached
context, prompt asking for 50-100 tokens situating the chunk. Prepend
the returned context to the chunk before embedding + tsv indexing.

### 4. Cloud SQL: on-cloud from M2, not local docker first

Discussed but never formally committed in a doc. **Effective decision**:
Cloud SQL from M2 onward because you know GCP well and don't want to
learn Docker Postgres just to save $30/month. Auto-stop via
`activation-policy=NEVER` will handle cost control.

### 5. Embedding: switch from text-embedding-005 to Gemini Embedding 2

Approved in Learning 10 but the current `phase2-selfbuilt.md` still
mentions text-embedding-005 in a few places (§4.4). **M2/M3 task**:
sweep the doc, update to Gemini Embedding 2, adjust `vector(N)`
dimension in schema.sql accordingly.

### 6. RAGAS: integrate before Phase 2 baseline is published

Not just "eventually" — it's an explicit deliverable of M6. Without
faithfulness + answer_relevance, the A/B report compares Phase 1 vs
Phase 2 on keyword score alone, which per `learnings/05` is a
pre-filter, not a verdict.

---

## Things NOT decided yet (open questions)

- **Cloud Run deployment timing**: designed but not deployed. Might do
  during M6 to have a "deployed on cloud" story, might skip if time
  runs out. Not blocking.
- **Voyage rerank-2.5-lite as Phase 2.5 experiment**: mentioned in
  Learning 10 as a future controlled experiment. Not part of Phase 2
  proper.
- **What to do about Frontend during Phase 2**: bbox highlight in the
  PDF pane is designed (§8 of phase2 doc) but not wired. UI work not
  yet scheduled.
- **When to actually stop Phase 1's Vertex AI Search datastore**:
  keep alive for A/B comparison during M6, tear down after A/B report.

---

## What's next (M2 concrete action list)

If the next session (you or another engineer) wants to actually start
implementing Phase 2, here's the ordered task list:

1. **Provision Cloud SQL instance**
   - `db-f1-micro` tier, PostgreSQL 16, region us-central1
   - Enable pgvector + pg_trgm extensions via Cloud SQL Studio
   - Configure IAM database user; grant CREATE, SELECT, INSERT, UPDATE, DELETE
   - Set up automated stop (`activation-policy=NEVER` cron) if not
     developing daily

2. **Write `api/app/db/schema.sql`**
   - Books / Chapters / Chunks tables per `phase2-selfbuilt.md §3`
   - HNSW index on chunks.embedding
   - GIN index on chunks.content_tsv
   - **IMPORTANT**: adjust `vector(N)` dimension based on chosen
     embedding model (Gemini Embedding 2 has a different dim than
     text-embedding-005)

3. **Apply schema via Cloud SQL Studio**
   - Console → Cloud SQL → studio → paste + Run
   - Verify tables exist via `\d chunks`

4. **Write `api/app/db/connection.py`**
   - Copy the pattern from `phase2-selfbuilt.md §2.5`
   - Add env var support for PROJECT/REGION/INSTANCE
   - Add unit test using a local docker fallback for CI

5. **Write `api/app/db/rows.py`**
   - `BookRow`, `ChapterRow`, `ChunkRow` Pydantic models
   - `from_attributes=True` config already exists on ApiModel base

6. **Write `api/app/db/repositories.py`**
   - Start with `BookRepository.insert/get/list_all`
   - Then `ChunkRepository.insert` — leave hybrid_search stubbed

7. **Verify end-to-end**: seed one book manually, insert one chunk with
   a hard-coded 768-dim (or whatever Gemini Embedding 2 uses) vector,
   `SELECT` it back, confirm the round-trip works.

**Then M2 is done and M3 (ingestion pipeline) can start.**

> **Addendum (2026-07-07, pre-M2 design re-audit).** Four refinements were
> folded into the design docs before starting task 1:
> 1. **Embedding dimension resolved**: Gemini Embedding 2 at
>    `output_dimensionality=768` (native 3072 exceeds pgvector's 2000-dim
>    HNSW cap). `vector(768)` stands. L2-normalize before insert; task 7
>    additionally verifies the norm of one real API vector.
> 2. **Task 2 schema updated** (`phase2-selfbuilt.md §3`): `content_tsv` is
>    now a `GENERATED ALWAYS … STORED` column (was unpopulated — silent
>    BM25-empty bug), and a nullable `context_prefix` column lands now so
>    M3's Contextual Retrieval needs no ALTER. Embedding + tsv cover
>    `context_prefix || content`; citations display bare `content`.
> 3. **Task 4 scope**: `connection.py` is dual-mode
>    (`DB_MODE=cloudsql|direct`) so the CI test can run against docker
>    `pgvector/pgvector:pg16` — see §2.5.
> 4. **Task 1 extra check**: confirm pgvector ≥ 0.8 on the instance
>    (iterative index scans for the filtered-HNSW post-filter case, §5.1).

---

## Files organizational context

```
learnings/
├── 01–02   RAG eval strategy fundamentals
├── 03      Corpus pivot saga (history → OpenStax)
├── 04–06   Golden set methodology
├── 07      Vertex AI Search deployment traps
├── 08      Phase 1 baseline interpretation
├── 09      Vector DB landscape
├── 10      Phase 2 design audit against 2026
└── session-notes/
    └── 2026-07-07-phase2-design-locked.md   ← this file
```

`interview-guide.md` is the top-level 5-minute walkthrough.
`phase2-selfbuilt.md` is the Phase 2 design of record.

---

## Cost + budget context (for the next session)

- Budget alert: ¥2000/month (~$13 USD)
- Total spent so far: < $5 USD across Phase 1 + Learning 10 research
- Phase 2 M2-M5 expected monthly spend: ~$5 with auto-stop discipline,
  ~$8-15 without
- Cloud SQL is the main variable — everything else is trivial

---

## Interview-story continuity

If you continue this project on another device or in a new session, the
interview story you can tell doesn't reset:

> "This is a two-phase RAG project on GCP. Phase 1 is a managed
> baseline using Vertex AI Search — deployed, measured, gives me
> real numbers to compare against. Phase 2 is a self-built pgvector
> pipeline whose design I locked after a documented audit against
> 2026 best practices, adopting Anthropic's Contextual Retrieval
> technique among other changes. I'm implementing Phase 2 now,
> starting with schema and ingestion pipeline."

That's the elevator pitch. `interview-guide.md` has the extended
version.
