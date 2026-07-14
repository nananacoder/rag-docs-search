# ADR-005: Gemini Flash as LLM reranker, not a deployed cross-encoder

**Status**: Accepted, shipped (M4). **Known cost**: ~1-2s of the ~19.6s p50.

## Decision
Top-20 fused candidates → one Gemini Flash call scoring each 0-10 (JSON)
→ keep top-5. On any parse/API failure, fall back to RRF order —
reranking degrades, retrieval never fails. Score distribution logged per
query (if scores cluster 7-9 over ~100 queries, the reranker isn't
discriminating → switch to rank-position selection).

## Why not a cross-encoder endpoint
A cross-encoder is ~100ms vs our ~1s — but needs an always-on serving
endpoint, breaking the whole project's scale-to-zero cost model. At
personal-project QPS the latency trade is correct; revisit at 10+ QPS.

## Why not hosted rerank APIs (Voyage/Cohere)
Real quality/latency case (learnings/10 Adoption 3), but re-introduces
an opaque component mid-experiment. Tracked as the Phase 2.5 controlled
experiment: swap ONLY the reranker, hold everything else, measure.
