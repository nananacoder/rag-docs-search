# Phase 1 vs Phase 2 — A/B Report

**The controlled experiment**: same corpus (OpenStax Astronomy 2e, 1,151
pages), same generator (Gemini 2.5 Flash, same prompt), same golden set,
same harness. **Only the retrieval architecture changes.** Every score
delta below is therefore attributable to retrieval, not to the model, the
prompt, or the eval design.

> **Status**: keyword / citation / latency measured (both phases). RAGAS
> harness wired (`run_eval.py --ragas`) and the direct-Gemini judge
> **validated against real Gemini** (faithfulness correctly scored 0.667 on
> a crafted 1-of-3-unsupported-claims sample). The full 8-question paid run
> did NOT complete: on teardown day, outbound port 3307 to Cloud SQL was
> network-blocked (learnings/11 §9), and the instance was deleted to stop
> the daily storage cost. RAGAS cells stay `‹RAGAS›` — the DB is
> regenerable from ingestion caches if the run is ever finished. The
> retrieval A/B stands on the measured keyword/citation deltas below.

---

## 1. Headline

| Metric | Phase 1 (Vertex AI Search) | Phase 2 (pgvector self-built) | Δ |
|---|---|---|---|
| Avg keyword score | 18.54% | **86.46%** | +67.9 pts |
| Avg citation accuracy | 0.00% | **57.50%** | +57.5 pts |
| Avg latency (p50) | 3.5s | ~19.6s | +16s (rerank + longer grounded answers) |
| Faithfulness (RAGAS) | ‹RAGAS-P1› | ‹RAGAS-P2› | — |
| Answer relevancy (RAGAS) | ‹RAGAS-P1› | ‹RAGAS-P2› | — |
| Context precision (RAGAS) | ‹RAGAS-P1› | ‹RAGAS-P2› | — |
| Cost (full deploy + first run) | < $5 | ~$5 ingestion (one-time) | — |

## 2. Per-bucket keyword score — each zero-bucket had a named fix

| Bucket | Phase 1 | Phase 2 | The Phase 2 mechanism responsible |
|---|---|---|---|
| factual | 23.00% | 85.00% | chunk-level retrieval + hybrid + rerank |
| chapter_scoped | 16.67% | 66.67% | chapter-aware chunking + `chapter_id` metadata filter |
| cross_topic | 16.67% | **100.00%** | RRF fusion of BM25 + vector; rerank keeps multi-section coverage |
| figure_or_diagram | 0.00% | **100.00%** | Gemini Vision figure captions indexed as text |

The three buckets Phase 1 scored ≤17% are exactly the ones needing
chunk-level, cross-section, or visual retrieval — none of which
document-level managed search can do. Phase 2 addressed each with a
specific, measurable design choice.

## 3. Citation accuracy — from structurally impossible to real

Phase 1's 0% is not a tuning failure: Standard-tier Vertex AI Search
returns document-level snippets with **no page metadata**, so every
citation defaulted to `page=1` — hitting the expected range was impossible.
Phase 2's Document-AI-free ingestion (route B+: pymupdf) restores per-chunk
`(page, bbox)`, lifting citation accuracy to a real 57.5% and enabling the
Angular bbox highlight (the visible product win).

Remaining gap to 100%: figure chunks carry whole-image bboxes, which the
range check penalizes (figure bucket citation ~20%). Analyzed in
`eval/runs/phase2-pgvector-v1.md`; a page-level fallback for figure
citations is the candidate fix.

## 4. Latency — where the 19.6s actually goes

The `ef_search` sweep (`eval/runs/m5-ef-search-sweep.md`) showed retrieval
SQL is only ~0.2–0.3s. The budget is almost entirely the two Gemini calls
(rerank + generation). This is the honest cost of the quality gain and the
primary M-next optimization target (shorter rerank passages, streaming-first
UX, generation-length caps). It is NOT a database-tuning problem.

## 5. Cost engineering

Total for both phases — deploy, ingest, measure — **~$12**. Mechanisms:
scale-to-zero everywhere (LLM rerank, no serving endpoint), session-based
Cloud SQL, every paid ingestion stage cached + idempotent, and Document AI
($11.5) replaced by a ~$1 pymupdf + Gemini Vision path after measuring that
its unique value (bbox precision) doesn't move retrieval metrics. See
interview-guide §9.5 and ADR-006.

## 6. Qualitative case studies (5) — ‹to fill from the paid RAGAS run›

Planned side-by-side answer comparisons, one per interesting pattern:

1. **Slipher redshift (cross_topic)** — P1 landed on an unrelated figure
   caption; P2 fuses the Slipher + Hubble sections. *(answers on file in
   the run cards; RAGAS faithfulness Δ to be added)*
2. **H-R diagram (figure_or_diagram)** — P1 0%; P2 retrieves the
   Vision-generated caption. Does the caption actually ground the answer?
   (faithfulness will tell.)
3. **Kepler / Tycho Brahe data (factual)** — both answer; compare citation
   precision and grounding.
4. **A chapter_scoped query** — did the chapter filter help or over-narrow?
5. **A deliberately out-of-corpus question** — does Mode C refusal hold in
   Phase 2? (faithfulness should stay high by refusing, not confabulating.)

## 7. Hypotheses revisited (from technical-design §5.2)

- **H1** (hybrid improves rare-proper-noun recall ≥10%): supported —
  cross_topic 16.67%→100%. ‹confirm with RAGAS context_precision›
- **H2** (rerank adds 500–1500ms): supported and then some — the LLM
  rerank + longer answers dominate the 16s latency increase.
- **H4** (chapter-aware chunking helps "in Chapter X"): supported —
  chapter_scoped 16.67%→66.67%.
- **H3** (cost crossover): Phase 1 cheaper at zero load (no Cloud SQL
  idle); Phase 2's session-stop discipline keeps idle near-zero anyway.

## 8. Honest limitations

- Golden set is **8 questions** — directional, not statistically tight.
  Every number here is "on this small hand-verified set."
- RAGAS judge is Gemini (same family as generator) — bias cancels in the
  A/B delta but inflates absolute values (ADR-008).
- `context_recall` not computed: needs per-question reference answers the
  golden set lacks (golden-v2 task).
- Embedding is `gemini-embedding-001`, not Gemini Embedding 2
  (allowlist-gated); doesn't affect the managed-vs-self-built thesis.
- Phase 2 not deployed to Cloud Run — retrieval scores are identical
  local vs deployed; only latency profile would change.

---

*Source run cards: `eval/runs/phase1-discovery-engine-v1-tuned-prompt.md`,
`eval/runs/phase2-pgvector-v1.md`, `eval/runs/m5-ef-search-sweep.md`.
Regenerate Phase 2 with RAGAS: start Cloud SQL, then
`python eval/run_eval.py --api … --ragas --out eval/runs/phase2-pgvector-v2-ragas.md`.*
