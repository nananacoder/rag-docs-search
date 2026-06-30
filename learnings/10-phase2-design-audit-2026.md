# 10 — Phase 2 Design Audit Against 2026 RAG Best Practices

**Date**: 2026-06-18
**Tags**: phase2, audit, 2026, contextual-retrieval, colpali, rerank, embedding

## Question I started with
"The Phase 2 design was written ~6 months ago. RAG moves fast — what
has the industry settled on since then, and are any of my design choices
already outdated? What would a senior engineer audit catch?"

## Short answer
**6 out of 12 design choices hold up unchanged. 4 deserve concrete
updates. 2 are explicitly deferred to a future Phase 3.** The audit is
honest about what's worth adopting now vs. what's research-stage vs.
what's marketing.

---

## Audit verdicts at a glance

| # | Phase 2 design choice | 2026 verdict |
|---|---|---|
| 1 | Document AI Layout Parser for PDF parsing | ✅ Keep — still the right choice |
| 2 | `chunk_size=800, overlap=120`, chapter-aware splitter | ⚠️ **Adopt Contextual Retrieval prepend** |
| 3 | `text-embedding-005` (768-dim) | ⚠️ **Replace with Gemini Embedding 2** |
| 4 | Cloud SQL + pgvector HNSW (m=16, ef_construction=64) | ✅ Keep — GCP still recommends pgvector |
| 5 | Hybrid BM25 + vector + RRF (k=60) | ✅ Keep — still industry standard |
| 6 | Gemini 2.5 Flash as LLM reranker | ⚠️ **Consider Voyage rerank-2.5-lite** |
| 7 | Caption-figures-as-text multimodal | ✅ Keep — defer ColPali to Phase 3 |
| 8 | Router with 3 escalation rules | ✅ Keep |
| 9 | Per-chunk `(page, bbox)` citation | ✅ Keep — the Phase 1 win point |
| 10 | SQLAlchemy schema + raw SQL hybrid retrieval | ✅ Keep — already 2026-aligned |
| 11 | Same eval set as Phase 1 (controlled variable) | ✅ Keep |
| 12 | RAGAS planned, not yet integrated | ⚠️ Plan: add it as part of M6 |

Plus: 2 things to ADD that aren't in the current design.

---

## The 4 adoptions (most important changes)

### Adoption 1 — Contextual Retrieval (Anthropic, Sep 2024)

**What it is.** Before embedding each chunk and indexing it in BM25,
prepend a 50–100-token LLM-generated context that explains where the
chunk sits in the whole document. Example:

> Original chunk: *"The company's revenue grew by 3% over the previous quarter."*
> Contextualized: *"This chunk is from an SEC filing on ACME Corp's Q2 2023 performance; sales were $X, up from $Y. The company's revenue grew by 3% over the previous quarter."*

**Anthropic's measured results** (failure rate = 1 − recall@20):
- Contextual Embeddings alone: **35% reduction** in failed retrievals
- Contextual Embeddings + Contextual BM25: **49% reduction**
- Stacked with reranking: **67% reduction**

**Cost at our scale.** Anthropic reports $1.02 per million document
tokens with prompt caching. For OpenStax 2e (~700K document tokens after
deduplication, plus chunk-specific overhead), one-time preprocessing is
**~$2–4 USD** total — within Phase 2's budget. With prompt caching the
re-prepend cost is dominated by chunk-side tokens, not the document
re-read.

**Why this matters for textbooks specifically.** OpenStax 2e chunks
constantly reference earlier-defined terms ("as we saw in Chapter 5",
"recall the Doppler effect"). A bare chunk that says "this is why
spirals receded faster" makes no retrieval sense without the
context-of-Slipher-and-Hubble. Contextual Retrieval prepends exactly
that linkage.

**Verdict: ADOPT.** Add to Phase 2 design as part of M3 ingestion
pipeline. The implementation is a Gemini 2.5 Flash call per chunk with
the parent chapter as cached context. The cost-benefit is unambiguously
positive at our scale.

**Source**: https://www.anthropic.com/news/contextual-retrieval

### Adoption 2 — Replace text-embedding-005 with Gemini Embedding 2

**Current state.** `text-embedding-005` is the 2024 Vertex embedding
model. GCP's 2026 model listings show **Gemini Embedding 2** as the
current Gemini-family embedding model. The text-embedding-005 status
isn't explicitly marked "deprecated" in the page content I could fetch,
but it's not in the "recommended" Gemini-family listings either.

**Why this matters for Phase 2.** The original `phase2-selfbuilt.md`
chose 005 partly for "control variable" (similar generation to Phase 1's
unnamed Vertex embedding). But:
- Phase 1's embedding model was never knowable, so the control claim was
  always weak
- The A/B story is "managed vs self-built retrieval architecture", not
  "managed vs older embedding model"
- Gemini Embedding 2 is GCP's actively recommended 2026 default

**Verdict: ADOPT** — switch the Phase 2 design to Gemini Embedding 2.
Update the ADR for "embedding choice" to reflect: "Chose Gemini Embedding
2 (2026 GCP default) over text-embedding-005 (2024 vintage) once it
became clear the 'controlled variable' argument was illusory — Phase 1's
embedding identity was never knowable."

**Caveat.** I couldn't fetch the exact dimensions of Gemini Embedding 2
from the navigation-only page returned. **M2 task: confirm dimensions
and adjust schema `vector(N)` accordingly** before the first INSERT.

**Source**: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings

### Adoption 3 — Evaluate dedicated rerankers (Voyage rerank-2.5-lite)

**What's available in 2026.** Three reranker classes:
1. **LLM-as-reranker** (our current plan: Gemini 2.5 Flash with score-passages prompt)
2. **Cohere Rerank** — `rerank-v4.0-pro` and `rerank-v4.0-fast` (2026 latest, multilingual)
3. **Voyage rerank** — `rerank-2.5` (32K context) and `rerank-2.5-lite` (latency-optimized)

**Trade-off space.**

| Approach | Latency | Cost | Quality | Visibility |
|---|---|---|---|---|
| Gemini 2.5 Flash LLM rerank | ~500–1500ms (one batched call) | Token-based, cached | Strong but variable | Score reasoning logged via JSON |
| Voyage rerank-2.5-lite | <100ms typical | Per `search_unit` | "Strictly better than rerank-2 legacy" per Voyage | Score only, no reasoning |
| Cohere Rerank v4 | <200ms typical | Per query | Comparable | Score only |

**Why I won't fully replace Gemini for Phase 2.** The Phase 2 narrative
benefits from "I implemented an LLM reranker myself" — replacing with
Voyage's hosted service re-introduces an opaque component. But the
audit case for using a dedicated reranker is real: lower latency,
likely better quality, simpler to operate.

**Verdict: TRACK as Phase 2.5 work.** Phase 2 ships with Gemini Flash
reranker for the controlled A/B. Once the baseline is measured, run a
follow-up A/B with Voyage rerank-2.5-lite as a variable, holding
everything else equal. This is a cleaner experiment than swapping
during Phase 2 build-out.

**Sources**: https://docs.voyageai.com/docs/reranker | https://docs.cohere.com/docs/rerank-overview

### Adoption 4 — Wire RAGAS into the eval harness as part of M6

The current eval harness (Phase 1) uses keyword overlap + citation
accuracy only. The Phase 2 design mentions RAGAS in passing but doesn't
integrate it. After the audit, RAGAS faithfulness + answer relevance
should be live by the time Phase 2 baseline numbers are published —
otherwise the A/B report compares two systems on keyword-only metrics,
which is the cheap pre-screen, not the verdict (see [learnings/05](./05-keyword-set-design.md)).

**Verdict: ADD to Phase 2 M6 explicitly.** RAGAS integration is a
bounded task (~4 hours): install ragas, plug in Vertex Gemini as the
judge model, run against existing run cards. Add the four metrics
(faithfulness, answer_relevance, context_precision, context_recall) to
the markdown run card template.

---

## The 2 deferrals (research-stage or premature)

### Deferral 1 — ColPali / late-interaction over PDF page images

**What it is.** Skip OCR entirely. Render each PDF page as an image,
embed the page image as a multi-vector representation using a Vision
Language Model, retrieve by late-interaction matching (ColBERT-style)
against query embeddings.

**Status.** Published at ICLR 2025, models + benchmark (ViDoRe) open on
Hugging Face, actively maintained (latest revision Feb 2025). Authors
claim it "largely outperforms modern document retrieval pipelines while
being drastically simpler, faster and end-to-end trainable."

**Why I'm deferring it for Phase 2.**
- The Phase 2 story is "self-built retrieval with visible algorithm";
  ColPali requires a VLM (Vision-Language Model) infrastructure we don't
  yet have
- Multi-vector retrieval needs a different storage strategy than HNSW
  (typically MaxSim scoring over per-token embeddings) — replacing the
  whole Cloud SQL design
- Storage cost grows substantially per document with multi-vector

**Verdict: DEFER to Phase 3.** This is genuinely interesting research,
and the "no OCR" angle would dodge most of Phase 2's structural-noise
work entirely. But adopting it for Phase 2 means rewriting Phase 2.
Better to ship Phase 2 vs Phase 1 first, *then* spike ColPali as a
controlled-variable Phase 3 ("same Phase 1, same eval, only retrieval
architecture changes to ColPali").

**Source**: https://arxiv.org/abs/2407.01449

### Deferral 2 — GraphRAG over textbook structure

**What it is.** Microsoft Research's GraphRAG builds an entity-and-
relation graph from the corpus, then performs community-aware retrieval
that surfaces entities + their relationships rather than text chunks.

**Why I considered it.** Textbooks have natural graph structure
(concepts → defined-in-chapter → referenced-in-later-chapter).
cross_topic queries (which Phase 1 scores 0% on) would, in principle,
benefit from a graph.

**Why I'm deferring.** GraphRAG's value shows most clearly on
**enterprise knowledge bases with thousands of documents** where
discovering connections across docs is the hard problem. For a
**single 1,151-page textbook**, the cross-chapter linkages are already
visible to the LLM once retrieval returns chunks from the right pages.
Building a graph for one textbook is heavy lifting for marginal lift.

**Verdict: DEFER to Phase 3+ or until corpus scales to multiple books.**
The hybrid + reranker approach in Phase 2 should hit cross_topic
significantly higher than Phase 1's 0% — measure that first before
adopting a much more complex retrieval architecture.

**Source**: https://www.microsoft.com/en-us/research/blog/graphrag-unlocking-llm-discovery-on-narrative-private-data/

---

## The 6 holdups (design choices that survived the audit)

These choices are still right; the audit only confirmed.

### Hold 1 — Document AI Layout Parser for PDF
Even with Gemini 2.5 multimodal that can directly read PDFs, Document
AI Layout Parser remains the right choice for our use case: it gives
**typed block-level output with bbox** that's required for the Phase 2
"filter structural noise" and "per-chunk bbox citation" features.
Gemini reading the PDF would either lose layoutType or require us to
re-prompt for structure at every ingest.

### Hold 2 — Chunking strategy (chunk_size=800, overlap=120)
2026 industry consensus on chunk size hasn't moved meaningfully. The
real innovation is **contextual prepending** (Adoption 1) on top of the
same 800-token chunks. Semantic chunking and proposition-based chunking
exist but cost ~10× more for marginal recall improvement on textbook
prose.

### Hold 3 — Cloud SQL + pgvector
GCP's 2026 reference architecture still defaults to pgvector. The
upgrade path is **AlloyDB pgvector** (same extension, faster engine,
~25× cost for our scale). Verified in [learnings/09](./09-vector-db-landscape.md).

### Hold 4 — HNSW (m=16, ef_construction=64) parameters
GCP's RAG reference architecture **does not publish HNSW parameter
recommendations**. The pgvector README's defaults (m=16, ef_construction=64)
remain the conservative choice. M5 task: sweep `ef_search` against eval,
not the build-time parameters.

### Hold 5 — RRF (k=60) hybrid fusion
RRF with k=60 remains the documented industry default. Weighted-sum
fusion exists but requires per-corpus score normalization that adds
complexity without measured win at our scale.

### Hold 6 — Caption-figures-as-text multimodal
GCP's 2026 reference architectures don't make multimodal embedding
(CLIP-style) the default. Caption-as-text remains the simpler,
unified-pipeline choice. Phase 2 keeps it; if the figure_or_diagram
bucket still underperforms after caption-as-text, that's the signal
to upgrade — not now.

---

## 2 things to ADD that weren't in the current design

### Add 1 — Long-context shortcut check before any RAG decision

Anthropic's Contextual Retrieval blog opens with this observation: *"if
your knowledge base is under ~200,000 tokens (roughly 500 pages), you may
not need RAG at all — you can stuff the whole corpus into the prompt and
use prompt caching."*

OpenStax Astronomy 2e is **1,151 pages**, well above this threshold. So
RAG is genuinely needed. But the design should **document that this
check was performed** — it shows architectural judgment.

**To add**: a short subsection in phase2-selfbuilt.md acknowledging the
long-context-shortcut check and stating why our corpus is past it
(>1100 pages, ~700K tokens — RAG is required).

### Add 2 — Reranker score-calibration logging

Phase 2 should log every rerank's score distribution per query. After
~100 queries, if scores cluster tightly (e.g., everything 7–9), the
LLM rerank isn't really discriminating — switch to rank-position-based
selection. This is operational hygiene the original design missed.

**To add**: a metric in M5: `reranker_score_distribution_per_query`
logged as a histogram, reviewed before the A/B report.

---

## Prioritized changes to Phase 2 docs

If only doing one thing: **Adoption 1 (Contextual Retrieval)**. The cost
is trivial at our scale (~$3 USD one-time), and the improvement numbers
are the strongest of any single change available. It also reads as a
sophisticated architectural choice in interviews ("I read Anthropic's
2024 paper and adopted Contextual Retrieval after measuring my Phase 1
baseline").

If doing three: add Adoption 2 (Gemini Embedding 2) and Adoption 4
(RAGAS in eval).

Adoption 3 (Voyage rerank) is the cleanest follow-up experiment but
not Phase-2-critical.

---

## What's worth adding as new learnings/

Two follow-up learnings flow naturally from this audit:

1. **`learnings/11-contextual-retrieval-decision.md`** — full decision
   record for adopting Contextual Retrieval at our scale: why textbook
   corpora benefit specifically, prompt caching cost math at 700K corpus
   tokens, and the implementation sketch (Gemini Flash per chunk with
   parent chapter cached).

2. **`learnings/12-reranker-landscape-2026.md`** — three-way analysis
   of LLM-as-reranker / Cohere / Voyage with the trade-off framework
   from this audit, plus an honest "I chose Gemini Flash for Phase 2
   because the self-built narrative wins; Voyage is the Phase 2.5
   experiment." Companion piece to [learnings/09](./09-vector-db-landscape.md)
   but for the reranker layer.

---

## Takeaway

**6 months between design and audit produced exactly 4 actionable
updates** — that's healthy maintenance cadence, not panic. The biggest
takeaway: **Contextual Retrieval is the single highest-leverage 2026
addition** because its cost is bounded ($3 at our scale) and its
measured gain is substantial (35–49% recall@20 improvement before
reranking). Everything else either holds up, defers, or is a follow-up
experiment.

**The honest framing for interviews:** *"I designed Phase 2 in [month
X], then audited the design against current 2026 best practices before
M2 implementation began. Four updates resulted, the most significant
being Anthropic's Contextual Retrieval technique — chunk prefixes
generated by an LLM that situate each chunk in the broader document.
Their measured 35–49% recall gain stacks with the reranker, and at our
corpus size it costs $3 one-time. The other three updates: switching to
Gemini Embedding 2, integrating RAGAS into the harness, and tracking
Voyage rerank as a Phase 2.5 controlled experiment."*

Companions:
- [`learnings/09-vector-db-landscape.md`](./09-vector-db-landscape.md) — vector DB choice + GCP recommendation
- [`phase2-selfbuilt.md`](../phase2-selfbuilt.md) — the design under audit
