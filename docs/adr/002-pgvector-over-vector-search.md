# ADR-002: Cloud SQL + pgvector over Vertex AI Vector Search / dedicated vector DBs

**Status**: Accepted, shipped (M2). pgvector 0.8.1 on PostgreSQL 16.

## Context
Phase 2 needs vector ANN, keyword search, and relational metadata
(books/chapters FK) — and its core query joins all three.

## Decision
pgvector in Cloud SQL. The vector is a column, not a system: "scope to
Chapter 22" is a WHERE clause; hybrid fusion is one CTE; one database to
run, stop, and bill.

## Alternatives rejected
- **Vertex AI Vector Search**: managed opacity again (the thing Phase 2
  exists to remove), higher idle cost, no SQL joins.
- **Pinecone/Weaviate**: second system to operate + sync; weaker
  metadata filtering than SQL; overkill under ~1M vectors.
- **AlloyDB**: same extension, faster engine, ~25× cost — the documented
  upgrade path, not the start (learnings/09).

## Constraint that shaped the schema
HNSW on `vector` caps at 2000 dims → embeddings pinned to 768 via MRL
truncation (see phase2-selfbuilt §4.4).
