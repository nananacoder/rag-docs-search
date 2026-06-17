# Interview Guide — Project Walkthrough

A 5-minute project tour for interviews. Walks through what this project is,
what's actually been built, what's deliberately *not* been built, and the
data-driven story behind the two-phase strategy. Each section has a short
"in interviews, say…" or quotable line at the end.

For deep dives into specific decisions or debugging stories, see
[learnings/](./learnings/).

---

## 1. What this project is — in one sentence

A NotebookLM-style RAG system over OpenStax *Astronomy 2e* (1,151 pages, CC
BY-NC-SA 4.0), built in **two phases on the same corpus** to compare a
managed RAG service against a self-built pipeline, with the same generation
model (Gemini 2.5 Flash) and the same evaluation harness — so quality
differences attribute to the retrieval stack.

> **In interviews:** *"It's a personal portfolio project, but designed as a
> controlled experiment. Same corpus, same model, same eval — only the
> retrieval architecture changes. That's the whole point."*

---

## 2. The two-phase strategy at a glance

| | Phase 1 — Managed | Phase 2 — Self-built |
|---|---|---|
| **Retrieval backend** | Vertex AI Search (Discovery Engine), Standard tier | Cloud SQL + pgvector (HNSW) |
| **Chunking** | Google-internal, opaque | Hand-written, chapter-aware (`chunk_size=800, overlap=120`) |
| **Embedding** | Google internal model, opaque | `text-embedding-005`, 768-dim, batched + cached |
| **Keyword index** | Internal | Postgres `tsvector` + GIN (BM25) |
| **Retrieval logic** | Single `search` API call | Hybrid: vector + BM25 + RRF fusion + LLM reranker |
| **Multimodal** | Text-only retrieval (figures not exposed in results) | Document AI Layout Parser → Gemini Vision captions for figures/diagrams |
| **Citation granularity** | Document-level snippet (no page, no bbox) — entire 1,151-page PDF is 1 document | Per-chunk `(page, bbox)` from Document AI Layout Parser |
| **Generation** | Gemini 2.5 Flash, same system prompt | Gemini 2.5 Flash, same system prompt — **deliberately unchanged so quality deltas attribute to retrieval, not the model** |
| **Eval harness** | Same golden set, same metrics, same `run_eval.py` | Same golden set, same metrics, same `run_eval.py` — **frozen so quality deltas are real, not eval-design artifacts** |
| **Status** | ✅ Deployed, baseline measured | 🟡 Designed, not yet built |

**Status as of this writing:** Phase 1 is fully deployed with measured
baseline numbers. Phase 2 design is locked; implementation is the next
milestone.

---

## 3. Phase 1 — what I built vs what Vertex AI built

This is the most important section to internalize. **Phase 1 is "I gave a
PDF to a managed service and read its output."** Inside that managed
service is most of a RAG system — but I built almost none of it.

### What I built (small and explicit)

| Layer | What my code actually does |
|---|---|
| **Ingest trigger** | Upload PDF to GCS bucket; call `ImportDocuments` API (one shot) |
| **Retriever wrapper** | `discovery_engine.py` constructs `SearchRequest`, calls the engine's `serving_config`, maps returned snippets into project's `RetrievedChunk` dataclass |
| **Generation prompt** | `gemini.py` writes the system prompt (3-mode response framework — see §6 below), formats context blocks with `[n]` citation rules |
| **Citation footer** | Auto-append "Access for free at openstax.org" (CC BY-NC-SA attribution) |
| **API layer** | FastAPI + SSE streaming, CORS, book-filter parameter |
| **Eval harness** | `run_eval.py` with keyword-overlap and citation-accuracy scoring |

### What Vertex AI Search built (large and opaque)

| Layer | What Discovery Engine does internally — none of which I configured |
|---|---|
| **PDF parsing** | Reads the 1,151-page PDF, extracts text |
| **Chunking** | Splits text into chunks — I don't know the size, overlap, or boundary rules |
| **Embedding** | Generates vectors with some Google-internal embedding model — I don't know which one |
| **Vector index** | Builds an ANN index (HNSW-class, presumably) — I can't see the parameters |
| **Inverted index** | Builds a BM25-style keyword index — config not exposed |
| **Hybrid retrieval** | Combines vector + keyword + filters at query time — algorithm not exposed |
| **Snippet generation** | Produces highlighted excerpts from matching documents — extraction rules not exposed |

### Phase 1 in one sentence

> **"I dropped a PDF into Vertex AI Search, called the search API, fed the
> results to Gemini, and put the answer in front of the user. Every
> RAG-internal mechanism — chunking, embedding, indexing, ranking — was
> a managed black box."**

That tradeoff (less work, less control) is exactly what Phase 2 will
quantify.

### What I deliberately don't claim to know

It would be dishonest to describe the managed internals as if I'd
inspected them. The right framing for an interview is **"this is a
black box, and here's what its outputs tell me about its behavior"**:

- **Chunk size and overlap** — not exposed; I infer "document-level"
  retrieval behavior from the fact that a single 1,151-page PDF
  consistently returns one matching document per query
- **Embedding model identity** — not named in the docs; only that it's
  a Google-internal model
- **ANN algorithm and parameters** (HNSW vs IVF, m, ef_construction) — not exposed
- **BM25 stemming, language config, stop-words** — not exposed
- **Ranking / fusion algorithm** between vector and keyword — not exposed
- **Whether figures themselves are processed** vs just their captions —
  not exposed; I observe figure-caption *text* gets indexed (the Slipher
  query landing on a Stephan's Quintet caption proves this), but I have
  no signal on whether the image content itself is analyzed

**Saying "I don't know" about these is more accurate than guessing.** The
opacity itself is the architectural property — and the reason Phase 2
exists.

### What Gemini does (and doesn't do)

Common interview misconception: "Gemini does the RAG." It does not. In
Phase 1 Gemini does exactly **one** thing — generate the answer text
from already-retrieved snippets. Vertex AI Search did all the retrieval
work *before* Gemini saw anything.

What Gemini sees, in one request:

```
system prompt (mine):
  "You are a research assistant... Mode A/B/C... Cite with [n]..."

user prompt (mine, formatted from retriever output):
  "Context:
   [1] From OpenStax Astronomy 2e:
   <Vertex AI Search snippet text>

   Question: <user's question>"
```

What Gemini **does** in Phase 1:
- Read the context blocks
- Pick a response mode (Mode A: full answer / Mode B: partial with
  named gaps / Mode C: refuse with summary of what was retrieved)
- Stay strictly grounded — never invent facts beyond the context
- Insert `[n]` citations matching the numbered context blocks
- Append the "Access for free at openstax.org" attribution

What Gemini **does NOT do** in Phase 1:
- ❌ Decide which part of the PDF is relevant — that's Vertex AI Search
- ❌ Chunk the PDF — Vertex AI Search's internal chunker
- ❌ Compute embeddings — Vertex AI Search's internal model
- ❌ Rerank candidates — Phase 1 has no reranker (Phase 2 adds one)
- ❌ Look up page numbers — Standard tier doesn't expose them; nobody can

**In Phase 2 Gemini gains a second job: LLM reranker.** Two separate
Gemini API calls per query — one scores 20 candidate chunks 0–10 (`top-20
→ top-5`), then a *separate* call generates the final answer using the
same prompt as Phase 1. The model and the generator prompt don't change;
only the reranker step is new.

> **In interviews:** *"Gemini's job in Phase 1 is purely generation — read
> the context the retriever already prepared and write the answer
> grounded in it. Retrieval, chunking, embedding, ranking are all
> Vertex AI Search. Phase 2 adds one extra Gemini call before the
> generator — a reranker that scores candidate chunks. That's two
> Gemini calls per query in Phase 2: rerank, then generate. Same model,
> different prompts."*

---

## 4. The data flow, side by side

```
═══ PHASE 1 (live today) ═══

PDF
 │
 ▼
GCS bucket
 │
 ▼  ImportDocuments API (one-shot)
 │
┌──────────────────────────────────────────┐
│ Vertex AI Search (managed black box)     │
│  ┌─ PDF parsing                          │
│  ├─ chunking            ← can't see /    │
│  ├─ embedding model      ← can't choose  │
│  ├─ ANN index (HNSW-ish) ← can't tune    │
│  ├─ BM25 inverted index                  │
│  └─ ranking algorithm                    │
└────────────────┬─────────────────────────┘
                 │
                 ▼  search API → snippets
                 │
        my retriever (snippet → RetrievedChunk)
                 │
                 ▼
         Gemini 2.5 Flash (my prompt)
                 │
                 ▼
                User



═══ PHASE 2 (designed, not yet built) ═══

PDF
 │
 ▼
GCS bucket
 │
 ▼  Eventarc trigger → my worker
 │
┌──────────────────────────────────────────┐
│ My ingestion pipeline:                   │
│  ├─ Document AI Layout Parser            │ ← I call it, results visible
│  ├─ my chunking code (chunk_size=800)    │ ← I write the splitter
│  ├─ text-embedding-005 API               │ ← I choose the model
│  ├─ Gemini Vision (figure captions)      │ ← I write the prompt
│  └─ INSERT INTO chunks (Cloud SQL)       │ ← I own the schema
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Cloud SQL + pgvector                     │
│  ├─ chunks.embedding (vector(768))       │ ← I can SELECT it
│  ├─ pgvector HNSW index (m=16, ef=64)    │ ← I tune the params
│  ├─ tsvector + GIN index (BM25)          │ ← I configure the analyzer
│  └─ FK to books / chapters tables        │ ← I designed the schema
└────────────────┬─────────────────────────┘
                 │
                 ▼  hybrid retrieval SQL (vector + BM25 + RRF)
                 │
        my retriever
                 │
                 ▼  top-20 chunks
        Gemini 2.5 Flash (LLM reranker, my prompt)
                 │
                 ▼  top-5 chunks
         Gemini 2.5 Flash (same generator as Phase 1)
                 │
                 ▼
                User
```

**Pay attention to the column on the right of each Phase 2 block.** Every
single layer in Phase 2 has a "← I can …" label that says what's now in my
hands. That column is empty in Phase 1.

### How the A/B comparison is physically wired

Two architectures, same eval — but they have to share an API surface for
that to work in practice. The retriever is implemented as an interface,
with three swappable concrete classes:

```
api/app/services/retrieval/
├── base.py             # Retriever ABC — defines list_books() + retrieve()
├── mock.py             # MockRetriever — fixture data, no GCP calls
├── discovery_engine.py # DiscoveryEngineRetriever — Phase 1 (live)
└── pgvector.py         # PgVectorRetriever — Phase 2 (planned)
```

The FastAPI `/api/query` endpoint depends only on the `Retriever`
interface. Switching backends is one env-var change:

```
# .env
RETRIEVAL_BACKEND=discovery_engine    # Phase 1
# RETRIEVAL_BACKEND=pgvector          # Phase 2
# RETRIEVAL_BACKEND=mock              # local dev, no GCP
```

The eval harness talks to the API over HTTP — it never sees which
retriever is wired in:

```bash
# Same command, same golden set, same scoring — different backend
poetry run python eval/run_eval.py \
  --api http://localhost:8000 \
  --golden eval/golden/v1.jsonl \
  --out eval/runs/phase1-discovery-engine-v1.md
poetry run python eval/run_eval.py \
  --api http://localhost:8000 \
  --golden eval/golden/v1.jsonl \
  --out eval/runs/phase2-pgvector-v1.md

diff eval/runs/phase1-*.md eval/runs/phase2-*.md   # apples-to-apples
```

This is **what makes the A/B real**: the eval can't know what backend it's
hitting, so it can't be tuned for one or the other. The score deltas
between the two run cards are pure retrieval-architecture deltas — the
generator, the prompt, the eval set, and the harness are all bit-identical
between runs.

> **In interviews:** *"The retriever is an interface; mock, Phase 1, and
> Phase 2 are three implementations. The API endpoint and the eval harness
> never know which one's wired in — `RETRIEVAL_BACKEND` is the single
> switch. That's how I can run the same `run_eval.py` against both
> systems and get a real apples-to-apples diff. The interface boundary is
> what makes the controlled experiment physically possible."*

---

## 5. The Phase 1 baseline — and why "bad" numbers are the point

Phase 1 baseline run (8-question golden set):

| Metric | Mock (control) | Phase 1 |
|---|---|---|
| Avg keyword overlap | 19.8% | **18.5%** (after prompt tuning) |
| Citation accuracy | 0.00% | **0.00%** |
| Latency p50 | 1.7s | 3.0s |
| Cost (full deploy + first run) | $0 | **< $5 USD** |

Three observations to anchor the interview narrative:

### Observation 1 — Citation accuracy is 0%, on purpose
Standard tier returns document-level snippets, not chunks, and the snippets
have no page metadata. There is literally no page number in the response,
so I default to `page = 1`. **This is the single strongest motivation for
Phase 2 existing** — Phase 2's Document AI Layout Parser restores per-chunk
`(page, bbox)` and lifts citation accuracy from "structurally impossible"
to "whatever the parser actually achieves."

### Observation 2 — Three out of four buckets score 0%
Bucket scores: `factual` 23%, `chapter_scoped` 0%, `cross_topic` 0%,
`figure_or_diagram` 0%. The three zero-buckets are exactly the queries
that need multi-section synthesis or visual content — which document-level
managed retrieval can't do. **Each zero-bucket maps to a specific Phase 2
design choice** (chunk-level retrieval; hybrid BM25 for cross-topic;
Document AI + Gemini Vision for figures).

### Observation 3 — A 90% baseline would have been a red flag
If a managed search product hit 90% citation accuracy on this eval, my
first suspicion would be that the eval is leaking ground truth somehow.
Realistic numbers for this corpus + this tier are 0–25%. **Calibration on
unrealistic baselines is a stronger signal than chasing them.**

> **In interviews:** *"My Phase 1 keyword score was 18%. That sounds bad
> until you read what's behind it: Standard-tier Vertex AI Search literally
> cannot return page numbers, and document-level retrieval can't synthesize
> across chapters. Each zero-bucket maps to a specific Phase 2 design
> decision. The 'bad' numbers are the substrate the rest of the project is
> built on."*

Full analysis: [learnings/08-phase1-baseline-interpretation.md](./learnings/08-phase1-baseline-interpretation.md)

---

## 6. The prompt tuning story — what's fixable vs what isn't

After deploying Phase 1, I noticed the system was over-refusing — answering
"I don't find this in the sources" even when retrieval had partial info.
The diagnosis was **two stacked problems**: a prompt-level binary
(answer-or-refuse) on top of a retrieval-level limitation (truncated
snippets).

I rewrote the system prompt around three response modes:

```
MODE A — Full answer       (context fully covers the question)
MODE B — Partial answer    (context covers part; name what's missing)
MODE C — Not found         (context not relevant; describe what was retrieved)
```

Result: keyword score went from 11% to 18.5% (+65%). Two dead buckets
(`chapter_scoped`, `cross_topic`) came back to life from 0% → 16.7%.
**`figure_or_diagram` and `citation_accuracy` stayed at 0%** — confirming
those are retrieval limits, not prompt limits.

> **In interviews:** *"Knowing which knob fixes which problem is what makes
> this useful instead of a guess-and-check session. Prompt tuning got me
> all the easy wins. What's still 0% is the structural retrieval problem
> — and that's exactly what Phase 2 fixes."*

Full story: [learnings/08-phase1-baseline-interpretation.md § the
over-refusal pattern](./learnings/08-phase1-baseline-interpretation.md)

---

## 7. The console-side smoke test — structural noise

Beyond the eval harness, I tested queries directly in the Vertex AI Search
Console preview and found the most concrete failure mode of all:

| Query | Top snippet from Vertex AI Search |
|---|---|
| `Hertzsprung Russell diagram` | "Diagram 609 Key Terms…" |
| `Slipher spiral nebulae redshift` | "We'll be discussing these 'death shroud' nebulae… (b) Stephan's Quintet" |

Both are real text from the PDF. Both are **structurally useless** — the
first hit landed on the end-of-chapter Key Terms list, the second on a
completely unrelated figure caption.

This is **structure-blindness**: Standard tier indexes the entire 1,151
page PDF as one document and treats body text, glossary entries, figure
captions, and appendix indexes all as the same flat text stream. On short
queries, terse glossary entries (high keyword density) regularly outrank
explanatory body text.

**This isn't a bug — it's a property of managed RAG without per-block
type filtering.** Phase 2 fixes it by exposing Document AI's `layoutType`
field per block (`body-text` / `caption` / `list-item` / `heading`) and
filtering or down-weighting non-body text at index time.

Full diagnosis: [learnings/07-vertex-ai-search-setup.md § structural
noise appendix](./learnings/07-vertex-ai-search-setup.md)

---

## 8. The Phase 2 design — directly motivated by Phase 1 data

| Phase 1 failure mode (measured) | Phase 2 fix (designed) |
|---|---|
| Document-level retrieval, no chunks | Per-chunk indexing in Cloud SQL `chunks` table |
| 0% citation accuracy (no page metadata) | Document AI Layout Parser → per-chunk `(page, bbox)` |
| Single-chapter bias (chapter_scoped 0%) | Top-k retrieval surfaces multiple chunks; hybrid retrieval crosses sections |
| Cross-topic queries fail (0%) | RRF fusion of vector + BM25; LLM reranker |
| Figure questions fail (0%) | Gemini Vision generates captions for diagrams; embedded as text |
| Structural noise (Key Terms outranks body) | Filter Document AI blocks by `layoutType`; skip `list-item` / `caption` from main index |

This isn't "I designed Phase 2 to be better" — it's "I read what was
broken, and each architectural choice maps to a specific failure I
measured."

The full Phase 2 design with schema, SQL, and tradeoffs:
[phase2-selfbuilt.md](./phase2-selfbuilt.md)

---

## 9. What I deliberately chose NOT to build

A real signal of project judgment is what's missing on purpose. Examples:

- **Phase 1 was not deployed to Cloud Run.** I designed the deployment
  (`infra/setup.md`), but for a Phase 1 baseline that already produces the
  same numbers locally, paying ~$5/month for visible cold starts adds zero
  to the project narrative. Phase 2 will deploy because Cloud SQL needs to
  run continuously.
- **The corpus pivoted from history books to OpenStax astronomy.** Original
  design assumed Project Gutenberg PDFs. They turned out to only exist as
  scans (no text layer) or in copyright-protected modern editions. OpenStax
  is CC BY-NC-SA 4.0, real text PDF, ~1,151 pages, with figures —
  preserves every architectural goal while being legally clean. The
  attribution string is auto-appended to every answer.
- **Eval set is hand-written, not LLM-synthesized.** 8 questions verified
  against PDF. Caught 9 audit bugs in the first pass — including a schema
  bug (`expected_book` couldn't represent cross-topic) that would have
  silently broken the eval if not caught at audit. The full audit log
  shows what audit actually catches.
- **Embedding model not upgraded for Phase 2 (yet).** Stayed on
  `text-embedding-005` instead of upgrading to Gemini Embedding 2.
  Reasoning: Phase 2's value proposition is "self-built vs managed
  retrieval," not "newer embedding model." Switching the model would
  confound the A/B comparison. A future Phase 3 could test the embedding
  upgrade as a separately controlled variable.

> **In interviews:** *"Knowing which battles to fight matters as much as
> winning them. I deliberately stopped at Phase 1 baseline before
> deploying anywhere; I picked OpenStax over a 'better' but legally
> ambiguous corpus; I locked the embedding model so Phase 2's win can't
> be confounded. None of these are technically interesting — they're
> all about not letting scope creep destroy the experiment."*

---

## 10. The biggest engineering moments — and where to find them

These are the project's "show me a hard thing you debugged" stories. Each
links to its full writeup in `learnings/`.

| Moment | The challenge | Where to find it |
|---|---|---|
| Vertex AI Search REST API setup | 6 traps in a row (ADC quota project, regional endpoint, missing `collections/` path, async client conflicts, Standard tier extractive segments, generator stub) | [learnings/07](./learnings/07-vertex-ai-search-setup.md) |
| Phase 1 baseline interpretation | Why "bad" numbers were correct, what prompt tuning could fix, what it couldn't | [learnings/08](./learnings/08-phase1-baseline-interpretation.md) |
| Golden set audit | 9 bugs caught in 7 questions; schema rewrite mid-audit; convention lock-down | [learnings/04](./learnings/04-golden-set-design-playbook.md) |
| Why I keep keyword scoring at all | Keyword vs LLM-judge tradeoffs, the two dimensions of "leniency" | [learnings/05](./learnings/05-keyword-set-design.md) |
| Eval at industrial scale | Four-layer pyramid (golden / synthetic / online / production logs); honest scope of this project's coverage | [learnings/06](./learnings/06-golden-set-at-scale.md) |
| Why eval comes before deploy | Eval as requirements doc + completion definition + value proof | [learnings/02](./learnings/02-eval-before-deploy.md) |
| Corpus pivot | History books → license walls → JLPT detour → NASA report mismatch → OpenStax | [learnings/03](./learnings/03-corpus-pivot-saga.md) |

---

## 11. Stack at a glance

| Layer | Tech |
|---|---|
| Frontend | Angular 19, standalone components, signals, Material 3, pdf.js |
| Backend | FastAPI, Pydantic v2, Poetry, structlog |
| Generation | Gemini 2.5 Flash via google-genai (Vertex mode) |
| Retrieval (P1) | Vertex AI Search Standard tier |
| Retrieval (P2) | Cloud SQL + pgvector HNSW, BM25 (tsvector), RRF, LLM reranker |
| Compute | Cloud Run (scale-to-zero) — designed but not yet deployed |
| Events | Eventarc on GCS finalize → worker (Phase 2) |
| Observability | Cloud Logging (structured JSON), Cloud Monitoring dashboards |
| IaC | Hand-authored `gcloud` runbook (`infra/setup.md`), not Terraform |
| Eval | Hand-written golden set + Python harness; markdown run cards committed to git |

---

## 12. The one-line summary

If I have to pitch this in a single sentence:

> *"Two RAG architectures on the same corpus, same generator, same eval —
> measure what you give up by going managed, then measure what you get
> back by going self-built. Each Phase 2 design choice maps to a specific
> Phase 1 failure I measured."*
