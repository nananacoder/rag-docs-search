# Phase 2 — Self-built Implementation (GCP primitives, no Vertex AI Search)

> **Goal.** Replace every managed "black box" from Phase 1 with a first-principles implementation, keeping generation and evaluation identical so differences attribute to the retrieval stack. Produce a direct A/B vs Phase 1 on the **same OpenStax *Astronomy 2e* corpus**, and gain deep ownership of chunking, embedding, vector storage, hybrid retrieval, reranking, and multimodal ingestion.

**Timeline:** ~4 weeks of evenings. **Prerequisite:** Phase 1 baseline metrics recorded (see [phase1-managed.md §8](./phase1-managed.md)).

See [technical-design.md §5](./technical-design.md) for the component comparison matrix.

---

## 1. What Changes vs Phase 1

| Layer | Phase 1 | Phase 2 |
|---|---|---|
| PDF parsing | Vertex AI Search built-in | **Document AI Layout Parser** (+ chapter heading detection) |
| Chunking | Auto | **Hand-written: chapter/section-aware recursive splitter** |
| Metadata | Basic structData | **Rich: book / author / chapter / section / page / modality** |
| Embedding | Managed | **Gemini Embedding 2** (`output_dimensionality=768`), batched, cached |
| Vector store | Vertex AI Search datastore | **Cloud SQL + pgvector** (HNSW) |
| Retrieval | Vector only | **Hybrid (BM25 + vector) with RRF** |
| Reranking | None | **Gemini 2.5 Flash as LLM reranker** |
| Multimodal | Layout-aware | **Gemini 2.5 Flash Vision → caption figures/diagrams → embed** |
| Router | Static (Flash only) | **Deterministic router with 3 escalation rules** |
| Citation UX | Page jump | **Page jump + bbox highlight** |

Unchanged on purpose: generation model, prompt template, eval harness, golden dataset, Angular UI shell. This is the scientific control.

---

## 2. Architecture (Phase 2)

```
              ┌────────────────────┐
     user ───▶│  Angular SPA       │
              │  (Cloud Run+nginx) │
              └──────────┬─────────┘
                         │ /api/query (SSE)
                         ▼
              ┌────────────────┐
              │ FastAPI `api`  │─────────────────┐
              │  (Cloud Run)   │                 │ Gemini 2.5
              └──┬──────┬──────┘                 │ (gen + rerank)
                 │      │                        │
                 │      └──► Router ──► escalate?│
                 │                                │
          query  ▼                                │
        ┌─────────────────┐                      │
        │ Retrieval       │                      │
        │  - BM25 (tsvec) │                      │
        │  - vector (HNSW)│                      │
        │  - RRF fusion   │                      │
        │  - rerank (LLM) │──────────────────────┘
        └────────┬────────┘
                 │
                 ▼
        ┌─────────────────────────────┐
        │ Cloud SQL (PostgreSQL 16)   │
        │  + pgvector                 │
        │  books, chapters, chunks,   │
        │  embeddings, tsvectors      │
        └────────▲────────────────────┘
                 │ upserts
                 │
        ┌────────┴────────┐       ┌──────────────────┐
        │ Worker (ingest) │───────│ Document AI      │
        │ (Cloud Run)     │       │ Layout Parser    │
        │ - parse         │       └──────────────────┘
        │ - chapter split │       ┌──────────────────┐
        │ - chunk         │───────│ Embedding API    │
        │ - embed (text)  │       │ text-embedding   │
        │ - caption (fig) │───────│ Gemini Vision    │
        │ - upsert        │       └──────────────────┘
        └────────▲────────┘
                 │ Eventarc
        ┌────────┴────────┐
        │ GCS raw bucket  │
        │ books/<id>/*    │
        └─────────────────┘
```

---

## 2.5 Technology Stack (2026 GCP-aligned)

This is the Python stack for the self-built pipeline. It is verified against
GCP's June 2026 official `cloud-sql-python-connector` documentation (v1.20.4),
the official `pgvector.asyncpg` integration, and GCP's documented
Cloud SQL Studio workflow for schema management.

### The stack

```
Cloud SQL for PostgreSQL 16
  ├─ pgvector extension                  ← vector storage + HNSW index
  └─ pg_trgm extension (optional)        ← fuzzy proper-noun match

Python application
  ├─ google-cloud-sql-connector v1.20.4  ← IAM-authenticated secure connection
  ├─ asyncpg                             ← PostgreSQL async driver
  ├─ pgvector.asyncpg                    ← registers vector type with asyncpg
  ├─ Pydantic 2.9                        ← API + DB row models (already in use)
  ├─ FastAPI 0.115 (already in use)
  └─ google-cloud-aiplatform             ← Vertex Embedding API + Gemini
```

**No SQLAlchemy. No Alembic. No ORM.** Pure Pydantic + raw SQL via
asyncpg, wrapped in Repository classes. Schema is hand-written `schema.sql`
in git, applied via Cloud SQL Studio (GCP's documented workflow).

### Why Pydantic + Repository, not SQLAlchemy ORM

The project already uses **Pydantic 2.9** for FastAPI request/response
validation (`api/app/models/*.py`). Phase 2 reuses Pydantic for database
row representation rather than introducing a parallel ORM modeling system.

| Concern | Pydantic + Repository (chosen) | SQLAlchemy ORM (rejected) |
|---|---|---|
| Schema definition | Hand-written `schema.sql` — the SQL is the source of truth | Python class auto-generating DDL — readers must mentally execute the class to know the SQL |
| Row representation | Existing Pydantic `ApiModel` extended into DB row models; `from_attributes=True` already configured | Parallel ORM classes mirrored from Pydantic via `model_validate(orm_instance)` — same fields written twice |
| Mental models in play | One (Pydantic across API + DB layers) | Two (Pydantic for API, ORM for DB, plus the conversion glue) |
| Complex retrieval (CTE + RRF fusion) | `await conn.fetch("WITH vec AS …")` — raw SQL is the natural fit | `session.execute(text("WITH vec AS …"))` — also raw SQL, but via an escape hatch |
| Simple CRUD (`INSERT chunk`) | Repository method with named asyncpg parameters | `session.add(Chunk(…))` — slightly terser, marginal gain |
| New dependencies | None added | +SQLAlchemy 2.x +pgvector.sqlalchemy +Alembic (if migrations are wanted) |

The decisive factor: **the most important queries in Phase 2 are raw SQL
either way**. ORM query-building doesn't apply to hybrid retrieval CTEs.
Outside of those queries, ORM would have added a parallel modeling system
on top of one this project already had working.

This also matches my prior production experience: FastAPI projects that
keep Pydantic as the unified data model and lean on Repository classes are
common in industry. The "ORM by default for everything" pattern is more
prevalent in Django-shaped projects.

### Why not `langchain-google-cloud-sql-pg`

GCP also ships an even higher-level library, `langchain-google-cloud-sql-pg`
(v0.15.0, Jan 2026), which provides a one-line `PostgresVectorStore` with
hybrid search and RRF built in. We **deliberately do not use it**, for the
same reason we don't use Vertex AI Search in Phase 2: it would re-introduce
a managed black box. Phase 2's value is "self-built retrieval where the
algorithm is visible and tunable" — wrapping everything in a LangChain
abstraction would re-create exactly the Phase 1 opacity problem.

This decision becomes an ADR (see §12 Exit Criteria).

### File layout

```
api/app/
├── models/                   # Pydantic API models (Phase 1, unchanged)
│   ├── book.py              # Book(ApiModel) — for frontend
│   ├── citation.py
│   └── query.py
│
├── db/                       # NEW in Phase 2
│   ├── connection.py        # google-cloud-sql-connector + asyncpg pool
│   ├── schema.sql           # CREATE TABLE / INDEX / EXTENSION — source of truth
│   ├── rows.py              # Pydantic models mirroring DB rows (BookRow, ChunkRow, …)
│   └── repositories.py      # BookRepository, ChunkRepository — SQL ↔ Pydantic
│
└── services/retrieval/
    └── pgvector.py          # Phase 2 Retriever implementation; calls ChunkRepository
```

### Schema management — GCP's documented Cloud SQL Studio workflow

Schema lives in **`api/app/db/schema.sql`** as hand-written DDL with
`IF NOT EXISTS` guards, committed to git as the single source of truth.
Anyone reviewing the project can read the SQL directly without
mentally compiling Python classes into DDL.

**For the initial bootstrap and ad-hoc schema changes**, we follow GCP's
documented workflow: paste `schema.sql` into **Cloud SQL Studio**
(Console → Cloud SQL → your instance → Cloud SQL Studio), authenticate
via IAM, click Run.

- This is GCP's officially documented UI for Cloud SQL schema work
  ([cloud.google.com/sql/docs/postgres/manage-data-using-studio](https://cloud.google.com/sql/docs/postgres/manage-data-using-studio))
- IAM auth means no password to manage
- For Phase 2's schema scale (~50 lines of DDL, runs in seconds),
  Studio's 5-minute statement timeout is irrelevant

**Why not Alembic / Flyway / Liquibase**: those tools shine when schema
evolves frequently across multiple developers, with concurrent merges
generating migration conflicts. This project is single-developer with
infrequent schema changes — the migration framework's complexity isn't
recouped. Documented as ADR. If the project grows past single developer
or schema changes per week, revisit.

**Local docker bootstrap** (for dev work before pushing to Cloud SQL):
```bash
docker exec -i rag-pgvector psql -U postgres -d rag < api/app/db/schema.sql
```

Or via gcloud against Cloud SQL:
```bash
gcloud sql connect rag-pg --user=rag-user --database=rag < api/app/db/schema.sql
```

Both are equivalent to pasting into Cloud SQL Studio — convenience-only
shortcuts for the same SQL.

### Cloud SQL connection pattern (GCP 2026 official)

```python
# api/app/db/connection.py
import asyncpg
from google.cloud.sql.connector import create_async_connector
from pgvector.asyncpg import register_vector

_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        connector = await create_async_connector()
        _pool = await asyncpg.create_pool(
            min_size=2, max_size=10,
            connect=lambda: connector.connect_async(
                f"{PROJECT}:{REGION}:{INSTANCE}",
                "asyncpg",
                user=DB_USER,
                db=DB_NAME,
                enable_iam_auth=True,    # ← no password; IAM-issued token
            ),
            init=register_vector,         # ← teaches asyncpg the vector type
        )
    return _pool
```

Notes:
- `enable_iam_auth=True` means **no password in env vars** — the Cloud Run
  service account authenticates via IAM.
- `register_vector` is the asyncpg-side equivalent of `pgvector.sqlalchemy`'s
  VECTOR type — it lets asyncpg send/receive `vector(N)` columns as Python
  lists or numpy arrays without manual JSON wrangling.
- For Cloud Run, also pass `Connector(refresh_strategy="lazy")` per GCP's
  June 2026 serverless guidance.

**Dual-mode for CI / local dev**: the connector path above requires GCP
credentials, which CI and local docker Postgres don't have. `connection.py`
therefore switches on an env var:

```
DB_MODE=cloudsql   # Cloud SQL connector + IAM auth (default; Cloud Run + dev-against-cloud)
DB_MODE=direct     # plain asyncpg.create_pool(dsn=DATABASE_URL) — CI / docker Postgres
```

Both modes pass `init=register_vector` so the `vector` type works
identically. The unit test in M2 runs against `DB_MODE=direct` + a
`pgvector/pgvector:pg16` container.

### Repository pattern — example

```python
# api/app/db/rows.py
from pydantic import BaseModel, ConfigDict

class ChunkRow(BaseModel):
    """Mirrors a row in the chunks table — flows through API + DB layers."""
    model_config = ConfigDict(from_attributes=True)
    chunk_id: int | None = None       # None when not yet inserted
    book_id: str
    chapter_id: int
    page: int
    bbox: dict | None = None
    modality: str = "text"
    content: str
    embedding: list[float]
    token_count: int

# api/app/db/repositories.py
class ChunkRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def insert(self, chunk: ChunkRow) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO chunks
                       (book_id, chapter_id, page, bbox, modality,
                        content, embedding, token_count)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   RETURNING chunk_id""",
                chunk.book_id, chunk.chapter_id, chunk.page, chunk.bbox,
                chunk.modality, chunk.content, chunk.embedding, chunk.token_count,
            )
            return row["chunk_id"]

    async def hybrid_search(
        self, query_vec: list[float], query_text: str, top_k: int = 20,
    ) -> list[ChunkRow]:
        """Hybrid BM25 + vector + RRF — see §5.1 for the full SQL."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(HYBRID_SEARCH_SQL, query_vec, query_text, top_k)
            return [ChunkRow.model_validate(dict(r)) for r in rows]
```

The retriever service holds a `ChunkRepository` instance and calls it.
The same Pydantic `ChunkRow` flows from the repository, through the
generation prompt assembly, back to the API response — no intermediate
conversions.

---

## 3. Data Model (Cloud SQL)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- optional, for fuzzy proper-noun matching

-- One row per book
CREATE TABLE books (
  book_id       TEXT PRIMARY KEY,
  title         TEXT NOT NULL,
  author        TEXT NOT NULL,
  year          INT,
  gcs_uri       TEXT NOT NULL,
  page_count    INT,
  source        TEXT,                     -- e.g. 'openstax'
  ingested_at   TIMESTAMPTZ DEFAULT now(),
  content_hash  TEXT
);

-- One row per chapter (or major section)
CREATE TABLE chapters (
  chapter_id    BIGSERIAL PRIMARY KEY,
  book_id       TEXT REFERENCES books(book_id) ON DELETE CASCADE,
  ordinal       INT,                      -- chapter 1,2,3...
  title         TEXT,                     -- "Chapter 22: Stars from Adolescence to Old Age"
  start_page    INT,
  end_page      INT,
  UNIQUE (book_id, ordinal)
);

-- One row per chunk
CREATE TABLE chunks (
  chunk_id      BIGSERIAL PRIMARY KEY,
  book_id       TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
  chapter_id    BIGINT REFERENCES chapters(chapter_id),
  page          INT,
  bbox          JSONB,                    -- {x0,y0,x1,y1} from Document AI
  modality      TEXT CHECK (modality IN ('text','table','figure','diagram')),
  content       TEXT NOT NULL,            -- VERBATIM text / table markdown / caption — what citations display
  context_prefix TEXT,                    -- M3 Contextual Retrieval: LLM-generated situating context (NULL until M3)
  content_tsv   tsvector GENERATED ALWAYS AS
                  (to_tsvector('english', coalesce(context_prefix, '') || ' ' || content)) STORED,
  embedding     vector(768),              -- Gemini Embedding 2, output_dimensionality=768 (MRL)
  token_count   INT,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX chunks_embedding_hnsw
  ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX chunks_tsv_gin   ON chunks USING GIN (content_tsv);
CREATE INDEX chunks_book      ON chunks (book_id);
CREATE INDEX chunks_chapter   ON chunks (chapter_id);
CREATE INDEX chunks_book_page ON chunks (book_id, page);
```

**Why this schema:**
- `books` / `chapters` / `chunks` three-table split mirrors how humans think about a textbook — and makes "scope query to *Astronomy 2e* Part III (Stars), Chapter 22" a single `WHERE book_id = ... AND chapter_id = ...` filter.
- `modality` distinguishes narrative text from figures/diagrams, which matters for the router's Pro-escalation rule.
- `bbox` on every chunk enables precise citation highlighting downstream.
- **`content` vs `context_prefix` split** (Contextual Retrieval, M3): `content`
  is always the verbatim source text — it's what the citation panel and bbox
  highlight show the user. `context_prefix` holds the LLM-generated 50–100
  token situating context. Retrieval sees the concatenation (embedding is
  computed over `context_prefix || ' ' || content`; the generated `content_tsv`
  column indexes the same concatenation → contextual BM25 for free). Display
  sees only `content`. The column is nullable so M2 can insert bare chunks
  before the M3 contextualizer exists.
- **`content_tsv` is a `GENERATED ALWAYS … STORED` column**, not an
  application-populated one. This removes an entire drift class: ingestion
  code can never forget to (re)compute the tsvector, and the BM25 side of
  §5.1 can never silently go empty.

**Why HNSW over IVF:** better recall at low-to-moderate dataset size (our target: <50k chunks for the 1,151-page *Astronomy 2e* split into 4 parts), no training step, online insert-friendly. IVF revisited above ~1M chunks.

---

## 4. Ingestion Pipeline

### 4.1 Parsing (Document AI Layout Parser)
- Input: book PDF from GCS.
- Output: structured blocks with `{page, bbox, type in [text, table, image], content}`.
- Fallback: if Document AI fails (rare; e.g. corrupted PDFs, > quota-per-doc pages), fall back to `pymupdf` for text-only extraction with a logged warning.
- **Chapter detection**: post-process text blocks to detect chapter headings. Heuristic:
  - Match patterns like `^Chapter \d+`, `^\d+\.\d+ ` (section headings), `^Appendix [A-Z]` — OpenStax 2e is consistently formatted.
  - Fall back to Document AI's heading-level signal (if `layoutType == "heading-1"` for chapters, `heading-2` for sections like `3.1 The Laws of Planetary Motion`).
  - Write a row to `chapters` for each detected chapter heading with inferred `start_page` and compute `end_page` as `next_chapter.start_page - 1`. Sections become rows in `chunks` linked to their parent chapter.
- This structure is the entire point — it's what lets Phase 2 answer "in chapter X" or "in section X.Y" questions better than Phase 1.

### 4.2 Chunking
Three strategies, selected by block type:

- **Text blocks (narrative)**: recursive character splitter with overlap. Start with `chunk_size=800, overlap=120`; validated via eval sweep. Every chunk inherits `book_id`, `chapter_id`, `page`, `bbox`.
- **Table blocks**: one chunk per table; content serialized to markdown. Split long tables by rows with header repetition.
- **Figure/diagram blocks**: one chunk per figure, content = Gemini-generated caption (§4.3), `modality='figure'` or `'diagram'` (heuristic: caption keywords `diagram`, `plot`, `chart`, `spectrum`, `H-R diagram`, or photograph-like aspect ratio).
- **Never split across chapter boundaries** — this is the key textbook-specific rule. A chunk belongs to exactly one chapter (and ideally one section).

### 4.3 Figure/diagram captioning (multimodal)
- For each image block, call Gemini 2.5 Flash Vision with prompt:
  *"This is a figure from an introductory astronomy textbook. Describe it in detail, including any axis labels, scientific quantities shown, celestial objects depicted, and explanatory annotations. If it is a diagram (e.g. H-R diagram, electromagnetic spectrum, galaxy classification chart), describe the structure and what each axis or region represents. Output only the description."*
- Cache captions keyed by `sha256(image_bytes)` in GCS — critical for large illustrated volumes.
- Caption text becomes the chunk content; embedded and BM25-indexed like regular text.

**Alternative considered:** multimodal embedding model (`multimodalembedding@001`). Rejected because: (a) captions-as-text give one unified BM25 + vector path, (b) captions are human-readable in the UI citation, (c) cheaper at current volumes. **Deliberate trade-off, recorded as an ADR.**

### 4.4 Embedding
- Model: **Gemini Embedding 2** (2026 GCP default; adopted over
  `text-embedding-005` per [learnings/10 audit](./learnings/10-phase2-design-audit-2026.md)).
- **Dimension: 768 via `output_dimensionality=768`** (MRL truncation from the
  native 3072; recommended truncation points are 768/1536/3072). Why not
  3072: pgvector's HNSW index caps at **2000 dims** for the `vector` type —
  native 3072 would force `halfvec`. 768 keeps `vector(768)`, i.e. the same
  storage/index footprint the design was originally sized for.
- **L2-normalize each vector before insert.** Sources disagree on whether
  truncated outputs come pre-normalized; normalizing is idempotent either
  way and guarantees cosine ≡ inner-product behavior. M2 exit check:
  print the norm of one real API vector.
- **Batch size 250** (API limit); retry with exponential backoff on 429/503.
- **Embed the contextualized text**: once M3's Contextual Retrieval lands, the
  string sent to the embedding API is `context_prefix || ' ' || content` — the
  same concatenation the generated `content_tsv` column indexes. Pre-M3 chunks
  embed bare `content` (prefix is NULL).
- **Cache** keyed by `sha256(text_sent_to_api + model_version)` → vector, stored in a GCS JSON (cheap, sufficient for personal project). Skip API call on cache hit — essential when re-running ingestion on config changes. Note the key is over the *contextualized* text, not bare `content` — a regenerated `context_prefix` must miss the cache.
- Track token usage per batch for cost dashboard.

### 4.5 Upsert
Idempotent: delete-then-insert all chunks for a `book_id` on re-ingest. Safe because the book is the natural transaction boundary. Use a single transaction so partial failures don't leave a half-indexed book.

---

## 5. Retrieval

### 5.1 Hybrid search (BM25 + vector + RRF)

```sql
WITH filtered_books AS (
  -- book_ids_param is the user's selected-books filter from the Angular left pane
  SELECT book_id FROM books
  WHERE ($book_ids_param IS NULL OR book_id = ANY($book_ids_param))
),
vec AS (
  SELECT chunk_id, 1 - (embedding <=> $query_embedding) AS score
  FROM chunks
  WHERE book_id IN (SELECT book_id FROM filtered_books)
  ORDER BY embedding <=> $query_embedding
  LIMIT 40
),
bm AS (
  SELECT chunk_id, ts_rank_cd(content_tsv, plainto_tsquery('english', $query_text)) AS score
  FROM chunks
  WHERE book_id IN (SELECT book_id FROM filtered_books)
    AND content_tsv @@ plainto_tsquery('english', $query_text)
  ORDER BY score DESC
  LIMIT 40
),
fused AS (
  SELECT chunk_id, SUM(1.0 / (60 + rank)) AS rrf_score
  FROM (
    SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank FROM vec
    UNION ALL
    SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank FROM bm
  ) t
  GROUP BY chunk_id
)
SELECT c.*, b.title, b.author, ch.ordinal AS chapter_num, ch.title AS chapter_title,
       fused.rrf_score
FROM fused
JOIN chunks c   USING (chunk_id)
JOIN books  b   ON b.book_id = c.book_id
LEFT JOIN chapters ch ON ch.chapter_id = c.chapter_id
ORDER BY fused.rrf_score DESC
LIMIT 20;
```

**Why RRF over weighted sum:** scale-free — no need to calibrate BM25 and cosine-similarity scores to the same range, which is fragile. `k=60` is the standard.

**Filtered HNSW caveat:** the `vec` CTE applies `WHERE book_id IN (…)` on top of
an HNSW scan — a post-filter. With a highly selective filter, HNSW can return
fewer than the requested 40 rows. pgvector ≥ 0.8's **iterative index scans**
fix this; M2 task: confirm the Cloud SQL PG16 instance ships pgvector ≥ 0.8.
(Low practical risk here — one book split into 4 parts is a weak filter.)

**Why hybrid matters for an astronomy textbook:** proper nouns and technical terms (Chandrasekhar, Carrington Event, Cepheid variable, Lagrange point, Schwarzschild radius, Andromeda) are where pure vector search is weakest — name-dropping queries hit BM25 exactly. This is directly testable with the eval set and a natural Phase 2 win.

### 5.2 Reranking
- Input: top-20 fused chunks.
- Call Gemini 2.5 Flash with prompt: *"Given this query: '<q>'. For each passage below, score 0–10 how useful it is for answering. Output JSON list of scores."*
- Keep top-5 by LLM score.
- Latency cost: 500–1500ms (one Flash call with batched passages).
- Log score distribution for calibration.

**Why LLM rerank over a deployed cross-encoder:** scale-to-zero (cross-encoder needs a running endpoint → cost). Trade-off: cross-encoder would be ~100ms vs our ~1s. Worth revisiting at 10+ QPS — but this is a personal project.

### 5.3 Query embedding cache
- `sha256(query_text + model_version) → vector` in per-instance LRU + persistent GCS.
- TTL 24h; invalidate on embedding model version change.

---

## 6. Router (full version)

```python
def route(query: str, retrieved: list[Chunk]) -> Literal["flash", "pro"]:
    # Rule 1: multimodal context present (figure/diagram chunk was retrieved)
    if any(c.modality in {"figure", "diagram"} for c in retrieved):
        return "pro"
    # Rule 2: explicit visual intent in the query
    visual_keywords = {"diagram", "figure", "chart", "plot", "spectrum", "h-r diagram", "graph"}
    if any(k in query.lower() for k in visual_keywords):
        return "pro"
    # Rule 3: low-confidence retrieval (rerank top-1 score is our best signal)
    if retrieved and retrieved[0].rerank_score < LOW_CONFIDENCE_THRESHOLD:
        return "pro"
    return "flash"
```

- Thresholds tuned on dev set, not test set.
- Every routing decision logged with the trigger rule → post-hoc the eval harness bucketizes by router decision to verify escalation actually improves faithfulness.

---

## 7. Generation (unchanged from Phase 1)
Same prompt template, same Gemini version, same SSE streaming, same citation validation. The prompt format is:
```
[1] From <authors>, <book title>, Ch. <num> ("<chapter title>"), p. <page>:
<chunk content>

[2] ...
```
This intentionally teaches the model to produce rich citations like *"...as discussed in Ch. 26 (Galaxies) [2]..."*. Every assistant response also surfaces the OpenStax attribution string ("Access for free at openstax.org") to satisfy the CC BY-NC-SA 4.0 redistribution requirement.

---

## 8. Citation UX in Angular (Phase 2 upgrade)

Because Document AI gives us bboxes and we store them on every chunk, the right-pane PDF viewer can now:
- Show answer with `[n]` citations in the center pane.
- On hover/click a citation: right pane jumps to the cited page **and draws a highlight rectangle over the source bbox**.
- Implementation: pdf.js / `ngx-extended-pdf-viewer` + a canvas overlay component that consumes `{page, bbox: {x0,y0,x1,y1}}` from the `/api/query` response and renders an SVG `<rect>` positioned in PDF coordinates.
- Add a small Angular `CitationHighlightService` (signal-based) that tracks which citation is active; clicking `[n]` in the answer pane updates the signal → the PDF pane effect fires page-jump + highlight.

This is a **concrete, demo-able improvement** over Phase 1 that makes the "we rebuilt the pipeline" story visible in 5 seconds during a demo.

---

## 9. A/B Comparison Deliverable

Produce a single markdown report `eval/runs/phase2-vs-phase1.md`:

### 9.1 Quantitative
| Metric | Phase 1 | Phase 2 | Δ | Winner |
|---|---|---|---|---|
| Faithfulness (RAGAS) | … | … | … | … |
| Answer relevance | … | … | … | … |
| Context precision | … | … | … | … |
| Context recall (by query_type) | … | … | … | … |
| Citation accuracy (book+chapter+page) | … | … | … | … |
| p50 end-to-end latency | … | … | … | … |
| p95 end-to-end latency | … | … | … | … |
| $ per query | … | … | … | … |
| $ per month idle | … | … | … | … |

Break out context recall by `query_type` (factual / chapter_scoped / cross_topic / figure_or_diagram) — that's where the Phase 2 wins should concentrate.

### 9.2 Qualitative — 5 Case Studies
Pick 5 representative queries from the golden set, show both systems' answers side-by-side, annotate *why* one is better. Must include at least one:
- Proper-noun-heavy query (BM25 win).
- Chapter-scoped query (chunking win).
- Figure/diagram query (multimodal pipeline win).

### 9.3 Hypotheses Revisited
Explicitly revisit H1–H4 from [technical-design.md §5.2](./technical-design.md). Mark each **confirmed / refuted / inconclusive** with data.

### 9.4 Honest Limitations
- Eval set size is small; confidence intervals noted.
- LLM-as-judge in RAGAS has known biases.
- Cost comparison depends heavily on QPS assumption.
- Chapter detection heuristic fails on non-standard Gutenberg formats (note which books).

Honesty here is itself a strong interview signal.

---

## 10. Cost Breakdown (Phase 2)

| Line Item | Idle | 100 q/day | Notes |
|---|---|---|---|
| Cloud Run (3 services) | $0 | $1–2 | scale-to-zero |
| **Cloud SQL (db-f1-micro)** | ~$8 | ~$8 | largest fixed cost; stoppable |
| GCS (raw + caches) | $0.50 | $1 | |
| Document AI Layout Parser | $0 | $1–2 | free tier for first N pages/month; big upfront cost on first ingest |
| Embedding API | $0 | < $1 | cached aggressively |
| Gemini 2.5 Flash (gen + rerank) | $0 | $2–3 | rerank is the biggest LLM cost |
| Gemini 2.5 Pro (router-gated) | $0 | $1 | ~10% of queries escalate |
| Gemini 2.5 Flash Vision (captions) | $0 | ~$0 | one-time per image, cached |
| Cloud Logging/Monitoring | $0 | $0.50 | |
| **Total** | **~$10** | **~$15–20** | |

**Crossover vs Phase 1:** Phase 2 has higher idle cost (Cloud SQL) but lower per-query cost (no Vertex AI Search per-query fee). Break-even where Phase 2 becomes cheaper: roughly where (P1 per-query × queries) > $8 (Cloud SQL). At ~$0.005/query, that's ~1600 queries/month ≈ 53/day. Confirm with real numbers in §9.

**Cost control tactic:** use `gcloud sql instances patch <name> --activation-policy=NEVER` to stop the instance between dev sessions (saves ~$8/month if you're not using it daily). Restart with `--activation-policy=ALWAYS`. Document both in the runbook.

---

## 11. What to Watch For (Pitfalls)

- **pgvector HNSW + `ef_search`**: too low = bad recall, too high = slow. Tune against the eval set, not by guessing. Record the recall curve.
- **HNSW index build memory on `db-f1-micro`**: 0.6 GB shared-core is tight for `maintenance_work_mem` during index build. At ~5–10k chunks × 768-dim it should pass (slowly); if the build OOMs, temporarily bump the instance to `db-g1-small` for the ingest run, then scale back down — no schema change needed.
- **Connection pooling**: Cloud Run + Cloud SQL can exhaust connections fast. We use **`google-cloud-sql-connector` v1.20.4 + `asyncpg.create_pool`** (per §2.5) — the connector handles IAM-authenticated TLS while asyncpg's built-in pool bounds connections. Starting parameters: `min_size=2, max_size=10`; tune based on Cloud Run `--concurrency` and observed `pg_stat_activity` saturation.
- **Embedding API rate limits**: batch sizing and backoff matter. Log 429s as a first-class metric.
- **Document AI quotas**: Layout Parser has monthly free quota; the initial 1,151-page *Astronomy 2e* ingest (split into 4 parts) will use a large slice — plan for it, and avoid full re-ingestion casually.
- **LLM reranker JSON output**: Gemini sometimes returns invalid JSON. Use structured output / function-calling mode, not free-form text.
- **BM25 language config**: default `english` tsvector handles plain prose well but **stemming is aggressive** (Chandrasekhar → chandrasekha), which can hurt scientific proper-noun recall. Consider `simple` config or a custom dictionary; validate on eval set.
- **Chapter detection false positives**: phrases like "see Chapter 5" appearing inside body text can false-match. Require heading-like formatting (short line, sentence-case, large font / heading layout signal from Document AI) before accepting.

---

## 12. Exit Criteria

Phase 2 is "done" when:
- [ ] All Phase 1 FRs remain satisfied on Phase 2 stack.
- [ ] A/B comparison report published with all 9 metrics filled in and query_type breakdown.
- [ ] Bbox-based citation highlighting works end-to-end in the Angular PDF pane.
- [ ] Eval pipeline wired into CI (Cloud Build) with regression gate.
- [ ] Full stack can be brought up from zero via updated `infra/setup.md` + `infra/scripts/*.sh`, torn down cleanly.
- [ ] ADRs written for:
  - Hybrid retrieval choice (BM25 + vector + RRF)
  - pgvector (Cloud SQL) vs Vertex AI Vector Search
  - **Pydantic + Repository pattern (asyncpg + raw SQL, no ORM) — reasoned rejection of both SQLAlchemy ORM and `langchain-google-cloud-sql-pg`** (see §2.5)
  - **Schema management via `schema.sql` in git + Cloud SQL Studio, deliberately deferring Alembic/Flyway** (see §2.5)
  - LLM rerank vs cross-encoder
  - Caption-based multimodal vs multimodal embeddings
  - Chapter-aware chunking strategy

The ADRs are the interview-day gold. Keep them short (1 page each) and opinionated.
