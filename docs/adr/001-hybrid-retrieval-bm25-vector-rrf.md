# ADR-001: Hybrid retrieval — BM25 + vector, fused with RRF(k=60)

**Status**: Accepted, shipped (M4). **Measured**: cross_topic 16.67% → 100% keyword.

## Context
Phase 1 measured two failure classes: semantic-only retrieval misses rare
proper nouns (Chandrasekhar, Cepheid — an astronomy textbook is full of
them), and keyword-only retrieval misses paraphrased questions.

## Decision
Run both retrievers per query — pgvector cosine top-40 and Postgres
`ts_rank_cd` top-40 — and fuse by Reciprocal Rank Fusion,
`score = Σ 1/(60+rank)`, in a single SQL CTE (§5.1).

## Why RRF over weighted-sum
Rank-based fusion is scale-free: BM25 scores are unbounded, cosine is
[0,1]; calibrating them to one scale is fragile per-corpus work. k=60 is
the Cormack et al. default; chunks hit by both lists rise naturally.

## Honest limitation
`ts_rank_cd` is cover-density ranking, not true BM25 (no corpus IDF /
length normalization). Adequate at 3k chunks; ParadeDB would be the true-
BM25 upgrade if the corpus grows 100×.
