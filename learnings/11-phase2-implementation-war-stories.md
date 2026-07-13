# 11 — Phase 2 Implementation: Seven War Stories (M2–M4)

**Date**: 2026-07-13
**Tags**: phase2, debugging, ingestion, pgvector, eval
**Result context**: Phase 2 went from zero code to a measured A/B in three
sessions: **keyword 18.54% → 86.46%, citation 0% → 57.5%** (see
`eval/runs/phase2-pgvector-v1.md`). These are the seven things that broke
or nearly broke along the way. Each maps to a general engineering lesson.

## 1. The chapter-detection design was wrong — real data said so

§4.1 assumed body text contains "Chapter N: Title" heading blocks. A free
pymupdf dry run on the real 1,151-page PDF: **regex found 0 chapters**.
Reality: chapter openers only contain a "Chapter Outline" block; the
chapter names live in the TOC. Fix: the PDF bookmark outline
(`doc.get_toc()`) — **43/43 chapters + appendices, exact start pages**.
Regex demoted to fallback.

> **Lesson**: heuristics over real documents must be written *after*
> looking at 20 real samples, not before. The free dry run that caught
> this cost $0.

## 2. strict mypy caught a bug that only fires in the cloud path

asyncpg pools call a custom `connect` callback with kwargs (`loop`,
`connection_class`, `record_class`). My cloudsql-mode closure took zero
args — a guaranteed TypeError on the *first real Cloud SQL connection*,
invisible to every local test (local runs use the direct-DSN path).
mypy's overload check flagged it pre-commit; source inspection of
`Pool._get_new_connection` confirmed.

> **Lesson**: each verification layer covers different blind spots. Type
> checking reached a code path integration tests structurally couldn't.

## 3. pgvector-python 0.5.0 returns `Vector`, not numpy arrays

First DB round-trip crashed: the decoded embedding is a non-iterable
`Vector` object (older versions returned ndarray). Fixed in the pydantic
validator (`.to_list()` first, iteration fallback).

> **Lesson**: round-trip tests exist to reconcile the library's actual
> behavior with your memory of it — before paid environments get involved.

## 4. "Is the truncated embedding normalized?" — settled by a $0.0001 probe

Sources conflicted. One real API call: **norm = 0.587 — NOT normalized**.
Manual L2 normalization went from "defensive" to "mandatory". The same
probe run revealed story 5.

> **Lesson**: when documentation disagrees, a one-call experiment beats
> another hour of reading.

## 5. The designed embedding model wasn't actually available

`gemini-embedding-2`: 404 in this project. `-2-preview`:
FAILED_PRECONDITION (allowlist-gated). Shipped with **gemini-embedding-001**
(GA Gemini-family, same MRL truncation mechanics, 768-dim confirmed).
Recorded in config with a revisit-when-GA comment; cache keys include the
model name so a later swap can't silently mix vector spaces.

> **Lesson**: model availability is a per-project runtime fact, not a
> docs fact. Probe before building a 3,000-call pipeline on a name.

## 6. A 429 killed the first ingestion run — cache design decided the blast radius

8-way concurrency hit Vertex's RPM quota mid-run. The captioner had a
sha256 cache → **all 678 figure captions (~$1.5) survived**. The
contextualizer had no retry and no cache → its spend evaporated. Fix:
shared tenacity backoff (429/503) on every LLM stage, contextualizer
cache added, concurrency 8 → 4. The rerun resumed from cache and finished.

> **Lesson**: every paid stage of a long batch job needs idempotency
> (cache) + resilience (retry) *before* the first real run. "Partially
> succeeded and resumable" is a design requirement, not a luxury.

## 7. First eval: keyword 79.6%, citation 0% — the golden set is a contract

Diagnosis: `book_match=False` on every question. The golden set's locked
convention (golden/README.md C-rules) expects book_ids
`openstax-astronomy-2e-pt{1-4}` mapped to chapter ranges; ingestion had
used a self-invented `astro-2e`. Fix: pure SQL migration reassigning
chunks/chapters to the four canonical part ids by chapter ordinal — zero
LLM cost. Citation went 0% → 57.5% without touching retrieval.

> **Lesson**: an eval set is an interface contract, not just test data.
> The producer (ingestion) must conform to it — and a metric that can
> say *book_match=False* pinpoints contract violations instantly.

## Route B+ postscript: the $11.5 that wasn't spent

Document AI Layout Parser prices at $10/1,000 pages with no free tier —
$11.5 for this corpus. Route B+ replaced it for now: pymupdf text +
pymupdf embedded-image extraction (678 figures after sha256 dedupe +
icon filtering) + Gemini Vision captions (~$1). What DocAI still uniquely
adds — precise per-block bbox and official layoutType — affects citation
highlight precision, not retrieval quality metrics. It remains a clean,
optional upgrade ingest. Total Phase 2 ingestion spend: **~$4-5**.
