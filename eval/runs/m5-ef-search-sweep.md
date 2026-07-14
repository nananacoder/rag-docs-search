# M5 — hnsw.ef_search sweep (retrieval-only, 2026-07-14)

**Method**: for each golden question (n=8), run the §5.1 hybrid SQL
(top-20) at each `ef_search`; score = expected-page-range hits among
returned chunks. Query embeddings served from cache; no rerank, no
generation — SQL-only, cost ≈ $0. Corpus: 3,028 chunks, HNSW m=16,
ef_construction=64, pgvector 0.8.1 on db-f1-micro.

| ef_search | recall@20 (≥1 hit) | avg in-range hits / q | p50 SQL ms |
|---|---|---|---|
| 10 | 8/8 | 4.4 | 770* |
| 20 | 8/8 | 7.4 | 278 |
| **40 (default)** | **8/8** | **7.4** | **262** |
| 80 | 8/8 | 7.4 | 186 |
| 150 | 8/8 | 7.4 | 182 |

\* ef=10 ran first and absorbs connection/plan warmup; treat latency
column as trend, not absolute. Depth (4.4 vs 7.4 hits) is the real ef=10
penalty.

## Findings

1. **Recall plateaus at ef_search=20** on this corpus (3k chunks is
   small for HNSW; the graph is easy to search). The pgvector default
   (40) sits comfortably on the plateau → **no change; keep 40.**
2. **Retrieval is ~0.2-0.3s of the ~19.6s end-to-end p50.** The latency
   budget lives almost entirely in the two LLM calls (rerank ~1-2s,
   answer generation the rest). M5 latency work should target the LLM
   side (shorter rerank passages, streaming-first UX, generation length)
   — NOT database tuning.
3. ef=10 shows the expected failure shape: same top-1-ish recall,
   thinner depth (4.4 vs 7.4 in-range hits) — depth is what the
   reranker feeds on, so under-provisioned ef would silently starve
   rerank quality before it shows up in recall@20.

**Decision**: `ef_search` stays at default 40. Recorded so the "did you
tune your index?" interview question has a measured answer: *"I swept
it; the knob doesn't matter at my scale — and I can show where the
latency actually lives."*
