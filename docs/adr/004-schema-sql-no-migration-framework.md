# ADR-004: schema.sql in git + Cloud SQL Studio; Alembic deferred

**Status**: Accepted, shipped (M2).

## Decision
One hand-written `api/app/db/schema.sql` with IF NOT EXISTS guards,
committed to git, applied via Cloud SQL Studio / psql / connector script
(all equivalent). No migration framework.

## Reasoning
Migration frameworks earn their complexity with multiple developers and
weekly schema churn (concurrent merges → migration conflicts). This
project: 1 developer, ~5 schema changes expected total. Even a 30-line
hand-rolled migration runner was rejected as over-engineering for that
cadence.

## Design consequence worth noting
Because the SQL file IS the schema, drift-prone derived state was moved
INTO the schema: `content_tsv` is a GENERATED ALWAYS column — ingestion
cannot forget to maintain it (this killed a silent-BM25-empty bug class
before it shipped).

## Revisit if
More than one developer, or schema changes become weekly.
