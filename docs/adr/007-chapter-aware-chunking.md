# ADR-007: Chapter-aware chunking (800/120) + Contextual Retrieval prefixes

**Status**: Accepted, shipped (M3). **Measured**: chapter_scoped 16.67% → 66.67% kw / 80% citation.

## Decision
Recursive splitter at ~800 tokens / 120 overlap that NEVER crosses a
chapter boundary; chapters resolved from the PDF bookmark outline
(learnings/11 story 1 — body-text heading regex found 0 chapters on the
real book). `list-item` blocks excluded from the index — the Phase 1
"Key Terms outranks body text" structural-noise fix. Each chunk carries
(book_id, chapter_id, page, bbox).

## Contextual Retrieval (Anthropic 2024) on top
Before embedding/indexing, each chunk gets a 50-100-token LLM-generated
prefix situating it in its chapter. Storage keeps `content` (verbatim,
what citations display) separate from `context_prefix`; embedding + the
generated tsv cover the concatenation — contextual BM25 for free.
Anthropic's measured 35-49% retrieval-failure reduction motivated
adoption; ~$3 one-time at this corpus size.

## Why not semantic/proposition chunking
~10× preprocessing cost for marginal gains on well-structured textbook
prose (2026 consensus per learnings/10 Hold 2). The chapter boundary is
the semantic boundary that matters here.
