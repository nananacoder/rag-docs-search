# 09 — Vector DB Landscape: Why pgvector for This Project (and What I Got Wrong)

**Date**: 2026-06-18
**Tags**: vector-db, pgvector, architecture-decision, market-research

## Question I started with
"Are all vector databases just relational SQL databases now? When I picked
PostgreSQL + pgvector for Phase 2, was that the default choice everyone
makes — or am I missing something the rest of the market knows?"

## Short answer
The market has **at least 4 different shapes** of vector storage — they are
not all SQL relational databases. PostgreSQL + pgvector is one shape (a
relational DB with a vector extension). For RAG over corpora in the
~thousands-to-millions-of-chunks range, it is a defensible default — but
not because it dominates the market. The market leader by raw deployment
is actually a search-engine class product (Elasticsearch). I picked
pgvector for project-specific reasons, not because "everyone uses it."

---

## 4 shapes of vector storage

Not every vector store is a SQL database. The shapes:

| Shape | SQL? | Examples |
|---|---|---|
| **A. Relational DB + vector extension** | ✅ Pure SQL | PostgreSQL + pgvector, SQLite + sqlite-vec, Oracle 23ai |
| **B. Cloud data warehouse with native VECTOR type** | ✅ Pure SQL | Snowflake, BigQuery (`VECTOR_SEARCH`), SingleStore |
| **C. Purpose-built vector DBs** | ❌ Their own API/SDK | Pinecone, Milvus, Qdrant, Weaviate, Chroma |
| **D. Search engines + vector support** | ⚠️ Their own JSON DSL | Elasticsearch, OpenSearch, Vespa |

Shape A and B feel like ordinary databases — you `CREATE TABLE` and `SELECT`.
Shape C is a separate service with its own client SDK; there's no `SELECT *`.
Shape D is an HTTP query language (JSON), not SQL.

This is the framing question matters most: **the choice of shape determines
the ecosystem you live in for everything else** (backups, ACID transactions,
JOINs, schema migrations, monitoring, hiring).

---

## What I confirmed about each (with sources)

### Shape A — Relational DB + extension

**pgvector** ([github.com/pgvector/pgvector](https://github.com/pgvector/pgvector))
- Latest tag in mid-2026: **v0.8.2** (Docker images include `0.8.2-pg18-trixie`)
- Supports both **HNSW and IVFFlat** index types per the README
- 21.8k GitHub stars
- The code we'll use: `CREATE EXTENSION vector;` then `embedding vector(768)` as a column type, queried with `<=>` (cosine distance), `<->` (L2), or `<#>` (inner product)

This is what Phase 2 chose.

### Shape B — Cloud data warehouse native VECTOR

**BigQuery `VECTOR_SEARCH`** ([docs](https://docs.cloud.google.com/bigquery/docs/vector-search-intro))
- GA (no preview label as of June 2026)
- Sibling `AI.SEARCH` function still in preview — useful distinction

**Snowflake `VECTOR` type** ([docs.snowflake.com](https://docs.snowflake.com/en/sql-reference/data-types-vector))
- Documented as a first-class type ("Snowflake supports a single vector
  data type, VECTOR")
- I could not find a specific GA date in 2024 or 2025 release notes; it
  is documented without preview labels, which is consistent with GA but
  not a hard confirmation.

### Shape C — Purpose-built (the names you've heard)

**Pinecone** — Serverless, SaaS only, pricing matters here:
- Standard plan: **$16–$18 per million read units**, $50/mo minimum
- Enterprise: $24–$27 per million read units, $500/mo minimum
- Storage: $0.33/GB/mo
- Source: [pinecone.io/pricing](https://www.pinecone.io/pricing/)

**Milvus** — 44.8k GitHub stars (highest in this category). Open source,
Kubernetes-native. Vendor-published benchmarks (VectorDBBench, run by
Zilliz, Milvus's vendor) consistently show it well, but **the benchmark
is not independent**. Treat "Milvus is #1" as a plausible vendor claim
rather than a settled fact.

**Qdrant** — Written in Rust ([github.com/qdrant/qdrant](https://github.com/qdrant/qdrant) self-describes:
"Qdrant is written in Rust 🦀, which makes it fast and reliable even
under high load"). 32.4k stars. Custom storage engine ("Gridstore").

**Chroma** — 28.5k stars. Originally pitched as Python-embedded for
local dev; the 2026 README has broadened beyond that ("the open-source
data infrastructure for AI"). Still common for prototypes.

**Weaviate** — GraphQL query API. Climbed DB-Engines rank from 12 → 9
between June 2025 and June 2026.

### Shape D — Search engines

**Elasticsearch** [dense_vector docs](https://www.elastic.co/guide/en/elasticsearch/reference/current/dense-vector.html):
"Dense vector fields are primarily used for k-nearest neighbor (kNN)
search." In Elastic Stack 9.4, the **default index** is `bbq_disk`
(binary-quantized on-disk) — a signal that the industry is moving toward
quantization-by-default for cost reasons.

**OpenSearch** documents a `knn_vector` field type with multiple engine
choices (Faiss, Lucene, NMSLIB).

---

## What I was wrong about (and you should know)

Three things I claimed in conversation that turned out not to hold up
when I checked:

1. **"pgvector is the most popular vector storage in 2026"** — partially
   wrong. By raw GitHub stars, Milvus (44.8k) and Qdrant (32.4k) both lead
   pgvector (21.8k). DB-Engines' June 2026 ranking puts **Elasticsearch
   #1** at 94.65, then OpenSearch (20.42), Couchbase, Pinecone, Kdb,
   Milvus. pgvector isn't even on that list because it's a Postgres
   extension, not a standalone DBMS — so the ranking under-counts it,
   but I cannot honestly call it "the most popular."

2. **"Pinecone serverless ~$0.30 per 1M reads"** — off by **roughly 50×**.
   Actual Standard plan: $16–$18 per million reads ($50/mo minimum). I
   confused storage pricing ($0.33/GB) with read pricing.

3. **"Milvus is the open-source benchmark leader"** — vendor benchmark
   (VectorDBBench is run by Milvus's vendor Zilliz). Plausible but not
   independently verified.

I'm flagging these because **the same kinds of soft claims — "most
popular," "fastest," "industry standard" — show up everywhere in vector
DB marketing**, and they bend the truth in similar ways. Audit the source
before quoting these numbers in technical decisions or interviews.

---

## What's actually shifted in 2026

Three trends with sources:

1. **Search engines are absorbing the vector workload.** DB-Engines' June
   2026 vector ranking puts Elasticsearch at 94.65 vs. OpenSearch at
   20.42 — a 4.6× gap to #2. The companies that already had search
   infrastructure are deploying vector capability and capturing the
   incumbent workloads.

2. **Pinecone moved up.** DB-Engines rank 6 → 4 between June 2025 and
   June 2026; Weaviate 12 → 9. Pure-play vector DBs are still gaining
   share, especially against legacy pre-LLM databases.

3. **Quantization-by-default.** Elastic Stack 9.4 ships `bbq_disk` (binary
   quantized, on-disk) as the default vector index. The industry signal:
   full 768-dim float vectors are not the ergonomic default anymore —
   compressed representations are.

---

## Why Phase 2 picked PostgreSQL + pgvector

Concrete reasons, not "everyone uses it":

| Decision factor | What pgvector gives me |
|---|---|
| **Corpus size** | OpenStax 2e at ~2,000 chunks. pgvector's HNSW handles up to ~10M chunks comfortably. Specialty stores' performance edge doesn't manifest at this scale. |
| **JOIN with metadata** | The `chunks` ↔ `chapters` ↔ `books` join enables "scope query to Ch.3" with one `WHERE chapter_id = …`. Specialty vector stores have weaker join models. |
| **One database for everything** | Vectors, full text (`tsvector`), inverted index (GIN), foreign keys, ACID transactions — all in one place. No separate vector service to operate. |
| **Already-known operational surface** | Backups, point-in-time recovery, monitoring, schema migrations — standard PostgreSQL playbook. No new tooling to learn. |
| **Cost predictability** | Cloud SQL `db-f1-micro` ~$8/mo idle. Pinecone Standard $50/mo minimum. For a personal project, the floor matters more than the ceiling. |
| **Phase 2 narrative** | "Self-built RAG using primitives I understand" reads better in interviews than "I added another SaaS to the stack." |

The single sentence: **pgvector is the default not because it's the
fastest, but because it's the smallest possible jump from the database
I already have.**

---

## Counter-arguments — when pgvector is the wrong choice

Honest about this: pgvector is not always the right answer. Reach for
specialty vector stores when:

- **> 100M vectors** — pgvector can scale this far with effort, but Milvus
  / Qdrant / Pinecone are designed for it
- **Sub-10ms p99 latency requirement** at high QPS — specialty stores
  have lower memory overhead and better quantization story
- **Multi-tenant SaaS isolation** — Pinecone's namespaces are simpler than
  rolling multi-tenancy in Postgres
- **You don't have a relational DB anyway** — bringing in PostgreSQL just
  for vectors is overhead; Chroma or Qdrant might be simpler
- **You want managed sharding / auto-scaling without ops work** — Pinecone
  serverless wins here

For Phase 2 of this project, none of these conditions hold. For other
projects, they might.

---

## What GCP officially recommends

GCP's RAG reference architectures spell out their preferred path with
concrete recommendations. Verified against
[`docs.cloud.google.com/architecture/rag-capable-gen-ai-app-using-vertex-ai`](https://docs.cloud.google.com/architecture/rag-capable-gen-ai-app-using-vertex-ai)
and the related architecture pages.

### The 5 vector storage options GCP discusses

| Product | Type | GCP recommends for |
|---|---|---|
| **AlloyDB for PostgreSQL + pgvector** | Relational + extension (Shape A) | **The primary architecture in GCP's RAG reference doc.** Production workloads where vectors live alongside transactional / analytical data |
| **Vertex AI Vector Search** (formerly Matching Engine) | Purpose-built (Shape C, GCP-native) | "Very large-scale vector-similarity matching" with "optimized serving infrastructure" — implied scale: hundreds of millions+ |
| **Cloud SQL + pgvector** | Relational + extension (Shape A) | The "Jump Start Solution" — quick experimentation and getting started |
| **Spanner Graph** | Specialized graph DB | GraphRAG specifically — when node relationships matter more than vector similarity |
| **Vertex AI Search / Gemini Enterprise** | Managed RAG (not strictly a vector DB) | Users who want fully-managed end-to-end RAG without composing the pieces themselves |

What GCP **does not** recommend or discuss in RAG architectures:

- **BigQuery vector search** — appears only in offline analytics / eval / log
  storage contexts, never as a primary vector store. GCP implicitly steers
  users away from BigQuery as the production retrieval layer.
- **Third-party vector DBs** (Pinecone, Milvus, Qdrant, Weaviate,
  Elasticsearch) — never mentioned in GCP RAG architecture pages, for
  obvious reasons. GCP's recommendations are GCP-native.

### GCP's implicit decision tree

GCP doesn't publish a flowchart, but their reference architecture pages
collectively encode this decision path:

```
What does your RAG project need?
│
├── "Just give me end-to-end managed RAG, I don't want to assemble parts"
│   └─→ Vertex AI Search / Gemini Enterprise
│       (This is what Phase 1 of this project uses)
│
├── "I want to build it myself; recommend a vector store"
│   │
│   ├── "Quick experimentation, ~thousands to ~millions of chunks"
│   │   └─→ Cloud SQL + pgvector ← GCP "Jump Start Solution"
│   │       (This is what Phase 2 uses)
│   │
│   ├── "Production scale, joining vectors with transactional data,
│   │    millions+ of chunks"
│   │   └─→ AlloyDB + pgvector ← GCP's primary RAG architecture
│   │
│   ├── "Hundreds of millions+ of vectors, sub-10ms p99 latency"
│   │   └─→ Vertex AI Vector Search
│   │
│   └── "GraphRAG (relationships matter more than similarity)"
│       └─→ Spanner Graph
```

### Why this matters for Phase 2's choice

**Two takeaways for our project's defense in interviews:**

1. **Phase 2's choice (Cloud SQL + pgvector) is on GCP's officially
   recommended path** — specifically the "Jump Start Solution" tier.
   We're not contradicting GCP guidance; we picked the entry-level
   product on the same recommended track that scales up to AlloyDB later.

2. **GCP itself treats pgvector as a first-class citizen** — both AlloyDB
   and Cloud SQL options use it. The market may show Elasticsearch and
   Milvus winning by raw deployment numbers, but **on GCP specifically,
   pgvector is the recommended default for relational-DB-shaped workloads**.

### Cloud SQL vs AlloyDB — why we didn't go to AlloyDB

The honest tradeoff:

| | Cloud SQL | AlloyDB |
|---|---|---|
| Minimum monthly cost | ~$8 (db-f1-micro) | ~$200 (smallest viable cluster) |
| PostgreSQL performance | Standard | ~4× faster (per Google's own benchmarks) |
| pgvector support | ✅ Yes | ✅ Yes, with internal optimizations |
| Comfort zone | < 1M vectors | > 10M vectors |
| Operational complexity | Simple | Higher (cluster, columnar engine, replicas) |

For a textbook with ~2,000 chunks, AlloyDB's performance edge is invisible
and its 25× cost premium isn't justified. Cloud SQL `db-f1-micro` sits
comfortably inside the budget alert. **The architectural upgrade path
exists** — if Phase 2 ever scales past Cloud SQL's comfort zone, the
migration is `pg_dump | gcloud alloydb import` and a connection-string
change. That option-value is enough; we don't need to pre-pay $200/mo
to keep it open.

---

## Interview-grade summary

If asked "why pgvector?":

> "Vector DB choice is a four-shape decision: relational with extension,
> cloud-warehouse native, purpose-built service, or search engine. I
> picked pgvector — relational + extension — because the corpus is
> small (~2,000 chunks), I need to JOIN vectors with chapter metadata
> for scoped queries, and one Postgres covers vector search, full-text
> BM25, and ACID metadata in the same database. Specialty stores like
> Pinecone or Milvus would win on raw scale and tail latency, but
> neither matters for a 1,151-page textbook. I'd revisit at 100M+
> vectors or sub-10ms p99 — neither applies here. The 2026 market
> reality: search-engine products like Elasticsearch are the actual
> volume leader, but they bring their own JSON query DSL — pgvector's
> SQL fit my mental model better."

---

## Takeaway

**The vector DB market is more shaped than market data suggests.** Four
distinct shapes serve different use cases; "popularity" depends entirely
on what you measure (GitHub stars, DB-Engines rank, raw deployments,
RAG-specific use). Defaulting to "the most popular vector DB" without
reading what shape it is and what scale it targets is exactly how
projects end up with a vector service they don't need.

**For RAG over a moderate corpus, pgvector is the smallest jump from
where you already are.** That is a stronger reason than "it's the most
popular" — and an honest one.

Companions:
- See [`phase2-selfbuilt.md`](../phase2-selfbuilt.md) §3 for the actual
  schema design
- See [`learnings/06-golden-set-at-scale.md`](./06-golden-set-at-scale.md)
  for a similar "industry trend with honest limits" framing applied to
  eval design
