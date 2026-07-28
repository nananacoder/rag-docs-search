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

## 8. RAGAS: a four-way dependency deadlock, solved by dropping the framework

Wiring RAGAS (the planned LLM-judged quality layer) hit a hard wall on
Python 3.12: every `ragas` version imports its judge through
`langchain_community.chat_models.vertexai`, a shim **removed** from current
langchain-community. Pinning back to the langchain 0.2 generation (which
still has the shim) then forces pydantic-v1 compat, which **crashes on
`langchain-google-vertexai`'s PEP-695 `TypeAliasType`**
(`RuntimeError: error checking inheritance of SafetySettingsType`). ragas ×
langchain × vertex × pydantic are mutually unsatisfiable without freezing
the whole stack to 2024 versions.

**Fix**: stop fighting the framework. The three metric *definitions*
(faithfulness, answer relevancy, context precision) are simple; I
reimplemented them as direct Gemini judge calls using the project's
already-working `google-genai` client — no langchain, no version pins.
Validated against a crafted sample (an answer with one deliberately
unsupported claim): **faithfulness scored 0.667**, correctly catching 1 of
3 claims as ungrounded; relevancy 0.9; precision 1.0.

> **Lesson**: same call as the no-ORM and no-LangChain-pg decisions —
> when a heavy framework fights the platform harder than the problem does,
> drop to the primitive. The metric is the deliverable, not the library.

## 9. The teardown-day network block

The full 8-question paid RAGAS run never completed: on teardown day, from a
different network, **outbound port 3307 (the Cloud SQL connector port) was
firewall-blocked** — every `retrieve()` timed out, though the same machine
connected fine two weeks earlier. Not fixable from the app side. Combined
with a cost-driven decision to tear down (the stopped instance still billed
~¥8/day storage), the call was: validate the judge against real Gemini
(done, §8), delete the instance, and let the already-measured
keyword/citation deltas carry the A/B. The DB is regenerable from the local
ingestion caches + `--split-astro-parts` if the run is ever finished.

> **Lesson**: managed-DB access depends on the *client* network, not just
> the instance. Cloud SQL's 3307 is a common corporate/ISP block — a proxy
> or private-IP path would dodge it. Also: cost pressure is a legitimate
> input to an engineering stop decision.

## Route B+ postscript: the $11.5 that wasn't spent

Document AI Layout Parser prices at $10/1,000 pages with no free tier —
$11.5 for this corpus. Route B+ replaced it for now: pymupdf text +
pymupdf embedded-image extraction (678 figures after sha256 dedupe +
icon filtering) + Gemini Vision captions (~$1). What DocAI still uniquely
adds — precise per-block bbox and official layoutType — affects citation
highlight precision, not retrieval quality metrics. It remains a clean,
optional upgrade ingest. Total Phase 2 ingestion spend: **~$4-5**.
