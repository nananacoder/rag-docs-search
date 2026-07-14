# ADR-003: Pydantic + Repository (raw asyncpg), no SQLAlchemy, no LangChain-pg

**Status**: Accepted after a documented reversal (f800f0d → ebc66bb), shipped (M2).

## Context
The project already models everything in Pydantic (FastAPI). The initial
decision followed "GCP-recommended" SQLAlchemy 2.x async; it was reversed
within hours.

## Decision
Hand-written `schema.sql` as source of truth; Pydantic row models
(`rows.py`); all SQL inside Repository classes (`repositories.py`);
asyncpg + pgvector codec.

## The decisive observation
Phase 2's most important queries (hybrid CTE + RRF) are raw SQL under
ANY stack — ORM query-building doesn't apply. ORM would only shorten
trivial INSERTs, at the cost of a second modeling system mirrored
against Pydantic.

## Also rejected
`langchain-google-cloud-sql-pg` (one-line PostgresVectorStore with hybrid
search built in): re-introduces a managed-style black box — exactly the
Phase 1 property this phase exists to remove.

## Revisit if
The team grows beyond one developer, or a query genuinely benefits from
an ORM query builder (ask that question first; usually no).
