# 01 — RAG Evaluation: Why "Classic + Standard" Means Adapting to Your Corpus

**Date**: 2026-05-20
**Tags**: eval, rag, ragas, design

## Question I started with
"Is golden-set + RAGAS + bucketed reporting just *the* way every Doc Agent gets evaluated?
Or do you have to change the strategy based on what's in the documents?"

## Short answer
The framework is universal. The buckets, the custom metrics, and the thresholds
**must** be designed for the specific corpus and the specific user-facing promise.
That design step is what separates real eval from "we ran RAGAS."

---

## The universal framework (every RAG/Doc Agent shares this)

```
Golden set (human-written Q + expected answer/source)
    ↓
Eval harness (run system → collect answer + retrieved chunks)
    ↓
Metrics (compare and score)
    ↓
Run card (versioned report)
```

This shape is decades old in IR (TREC, BEIR). RAG just adds a generation layer on top.

## The universal RAG metric split

RAG fails in two distinct layers, so metrics split accordingly:

**Retrieval layer**
- **Context Recall** — were the right chunks retrieved?
- **Context Precision** — were the retrieved chunks relevant?
- **MRR / nDCG@k** — ranking quality

**Generation layer**
- **Faithfulness** — did the answer stay inside the context (no hallucination)?
- **Answer Relevance** — did it answer the question asked?

The four are **deliberately independent** so they localize failure:

| Recall | Faithfulness | Diagnosis |
|---|---|---|
| Low | High | Retriever is the bottleneck |
| High | Low | LLM is hallucinating |
| Low | Low | Both broken |
| High | High | System is healthy |

A single "average score" would hide this signal entirely.

---

## Why "classic + standard" is not "one size fits all"

The framework is universal, but the **content of the framework** must adapt:

### Bucket design (`query_type`) is corpus-specific

The four buckets in this project — `factual` / `chapter_scoped` / `cross_book` / `figure_or_map`
— were chosen because the corpus is *multi-book chaptered history with possible illustrations*.

For other domains the buckets must be redesigned:

| Domain | Buckets that make sense |
|---|---|
| **Legal contracts/case law** | `literal_clause`, `cross_reference`, `precedent_lookup` |
| **Medical papers** | `mechanism`, `dosage`, `contraindication`, `meta_analysis` |
| **Customer-support KB** | `how_to`, `troubleshoot`, `policy` |
| **Code repository QA** | `api_signature`, `architecture`, `change_history` |

Buckets aren't categories of questions — they're **categories of system capability**.
Each bucket should map to either (a) something the system claims to be good at, or
(b) something a planned upgrade is supposed to improve.

### Custom metrics fill RAGAS's blind spots

RAGAS's four metrics don't cover everything users care about. Domain-specific gaps:

| Domain | Custom metric needed | Why |
|---|---|---|
| **NotebookLM-style (this project)** | Citation accuracy (book + chapter + page in expected range) | RAGAS doesn't check if `[1] p.412` actually corresponds to p.412 — but the user's whole experience hinges on it |
| **Medical** | Numeric exact-match (dosage, units) | "5mg vs 50mg" is a clinical disaster but barely moves faithfulness |
| **Legal** | Clause completeness (no missing related clauses) | Citing one clause but missing its cross-reference is wrong |
| **Customer support** | Resolution rate (human judgment) | The *real* outcome metric — RAGAS can't infer it |

A heuristic: **whenever you can imagine a system that scores high on RAGAS but
still fails its users**, you need a custom metric.

### Thresholds are domain-specific too

A faithfulness of 0.85 is fine for a casual Q&A bot. For medical advice it's
unacceptably low — that 15% gap is hallucination on actual care decisions.
Threshold setting is a separate design step, not a universal default.

---

## Bucketed reporting hides nothing — averaging hides everything

A concrete made-up example:

| query_type | Phase 1 | Phase 2 | Δ |
|---|---|---|---|
| factual          | 0.85 | 0.82 | -0.03 |
| chapter_scoped   | 0.70 | 0.88 | +0.18 |
| cross_book       | 0.55 | 0.75 | +0.20 |
| figure_or_map    | 0.10 | 0.65 | +0.55 |
| **average**      | 0.55 | 0.78 | +0.23 |

The average says "Phase 2 is +23% better." That's true but uninformative.

The buckets say: *Phase 2 dominates on the work it was specifically designed to
improve (chapter-aware chunking, cross-book retrieval, multimodal pipeline) and
slightly regresses on the easy case (rerank adds noise to already-good queries).*

That second story is what an A/B comparison is actually for.

---

## Signals that you should adapt the eval strategy

While writing golden questions, watch for these — each is a hint that your
metric set is incomplete:

1. **A query where RAGAS scores high but the answer feels bad** → you're missing
   a custom metric. (This is exactly how citation accuracy enters the picture
   for NotebookLM-style systems.)
2. **A bucket scores 0.0 or 1.0 across the board** → no discriminative power;
   merge it or split it
3. **A class of questions you know the system can't answer** → make it a
   dedicated bucket *not* used for pass/fail thresholds, just for tracking
   capability boundaries
4. **The domain has objective ground truth (numbers, dates, names)** → add
   exact-match alongside LLM-judged metrics; LLM judges are flaky on numerics
5. **The domain has things the system must *not* say** (medical disclaimers,
   legal "this isn't advice") → add a negative-match check

---

## Specific implications for this project

The original design (`phase1-managed.md §3.9`) is well-thought-out:
- 30–50 hand-written questions: large enough for stable per-bucket averages,
  small enough to write in 2–3 sittings
- RAGAS quartet for the universal layer
- Citation accuracy added because NotebookLM-style systems live or die by source attribution
- Bucketed reporting tied directly to Phase 2's planned upgrades

But the bucket choices depend on **which books actually get selected**:
- If chosen books have **no illustrations** (many Gutenberg PDFs are pure text),
  `figure_or_map` should be replaced — perhaps with `name_heavy` (proper-noun-heavy
  queries that are pure BM25 wins, the textual analogue of "Phase 2 should beat
  Phase 1 on its self-built strengths")
- Translated works (e.g. Thucydides translations) introduce terminology variance —
  worth a `terminology_consistency` check
- Speech/letter collections (vs narrative history) would push `chapter_scoped`
  toward `speaker_scoped` or `date_scoped`

So the final book list isn't just a content decision — it's an eval-design decision.
Picking books, scanning their structure, and finalizing buckets is one combined step.

---

## Recent industry trends worth knowing

- **LLM-as-judge is now standard** (RAGAS is built on it) but has known biases:
  preference for longer answers, preference for the judge's own model family.
  Serious projects do **judge calibration** — manually labeling ~30 questions
  and checking that LLM scores correlate with human scores. This project's
  §9.4 honesty section already flags this.
- **Synthetic golden sets** (LLM generates Q&A from the corpus, humans filter)
  are common at scale, but for a portfolio/interview project, hand-written
  small sets are *more credible* because they prove domain familiarity.
- **Online metrics > offline metrics** for mature products (click-through, CSAT,
  thumbs-up rate). Not relevant here, but worth knowing the maturity ladder:
  *offline RAGAS → human eval → A/B tests → online metrics*.
- **Agent eval frameworks** (LangSmith, Braintrust, Phoenix) extend this pattern
  to multi-step tool-using agents, where the trajectory matters as much as the
  final answer.

---

## Takeaway

Eval is not template-following. It's a deliberate answer to:
**"What does 'good' mean in this domain, and what does my system specifically
promise users?"**

The classic framework gives you the *shape* (golden set + multi-layer metrics +
bucketed reporting + run cards). What you fill in — buckets, custom metrics,
thresholds, calibration — must be derived from your corpus and your product
promise. The two interview-worthy moments aren't "we used RAGAS." They are:

1. Why these specific buckets, given this corpus
2. Why these custom metrics, given the gaps in RAGAS for this domain
