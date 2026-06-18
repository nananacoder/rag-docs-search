# 06 — Golden Set at Industrial Scale: Beyond the Hand-Written 30

**Date**: 2026-05-28
**Tags**: eval, golden-set, scale, industry-practice

## Question I started with
"For a portfolio project, hand-writing 30–50 golden questions makes sense. But
real industrial RAG systems index millions of documents and serve millions of
queries. Surely they don't hand-write everything. So what *do* they do? And
how should that change my approach when the corpus grows?"

## Short answer
No serious industrial RAG project hand-writes hundreds of thousands of eval
questions, and no serious one purely auto-generates them either. The standard
pattern is a **layered approach** (small expert-written reference set + medium
synthetic set with spot-check + large auto-graded online set + production user
logs), with each layer serving a different purpose and confidence level.

---

## The four-layer pattern

This is a useful mental model — but **not a named industry concept**. Treat it
as my synthesis of what frameworks like RAGAS, OpenAI Evals, LangSmith, and
Anthropic's red-teaming work describe in pieces, not as a canonical "evaluation
pyramid" you can cite.

```
Layer 1 — Reference / Golden       50–500 questions    100% hand-written by SMEs
Layer 2 — Synthetic / Augmented    1k–10k questions    LLM-generated, 5–20% human spot-check
Layer 3 — Online auto-graded       10k–1M questions    LLM-judge, no per-question human review
Layer 4 — Production logs          continuous          real user queries, sampled review + feedback signals
```

Each layer has **different cost, different confidence, different purpose** — and
they're not redundant. Skipping any one of them leaves a real blind spot.

---

## Layer 1 — Reference / Golden Set

**Size**: 50–500 questions
**Authored by**: Domain SMEs (not engineers, not LLMs)
**Reviewed by**: Two-person rule — writer ≠ reviewer
**Cost**: 15–60 minutes per question, all-in (write + verify + review)
**Used for**:
- Major release regression gate ("does v2 still pass these?")
- Public-facing accuracy claims ("our system scores 87% on …")
- Compliance/audit material in regulated domains

**Why expensive but necessary**: this is the only layer where you can fully trust
the ground truth. The other three layers eventually anchor back to this one for
calibration.

**This project**: `eval/golden/v1.jsonl` — currently 8 questions, target 30–50.
This is Layer 1 only. No other layer exists yet.

---

## Layer 2 — Synthetic / Augmented Set

**Size**: 1,000–10,000 questions
**Authored by**: LLM, generated from corpus chunks
**Reviewed by**: Human spot-check on a sample (commonly cited as ~10–20%, though
no major framework publishes this number as a fixed standard — treat as
heuristic, not industry rule)
**Used for**:
- Broad coverage of the full corpus, not just SME-favored topics
- Surfacing blind spots in Layer 1 (questions of types SMEs forgot)
- Training and tuning data

**How it's typically generated** (the pattern documented in
[RAGAS testset generation](https://docs.ragas.io/en/latest/concepts/test_data_generation/rag/)):

```python
for chunk in corpus_chunks:
    qa = llm(f"Generate a user-style question whose answer is in this passage:\n{chunk}")
    qa["reference_contexts"] = [chunk.id]   # ground truth retrieval target
    augmented_set.append(qa)
```

The structural advantage: because the LLM **generated the question from a known
chunk**, that chunk is automatically the retrieval ground truth. This solves the
exact problem you hit in Bug 2 of `learnings/04` ("how do I verify
`expected_page_range`?") — the verification is implicit in the generation.

**Known biases of synthetic questions**:
- Skew toward "extractive" patterns ("What does X mean?") rather than the messy
  questions real users actually ask
- LLM-generated ground truth + LLM-judge scoring is partially circular if the
  same model family does both — typically mitigated by using different model
  families for generation vs. scoring (e.g. Gemini generates, Claude judges)
- Tend to under-represent multi-hop and figure/diagram questions

**RAGAS source**: https://docs.ragas.io/en/latest/concepts/test_data_generation/rag/
— their `QuerySynthesizer` produces `(user_input, reference_contexts, reference)`
samples that match exactly this pattern.

---

## Layer 3 — Online auto-graded eval

**Size**: 10k–1M+ questions
**Authored by**: LLM
**Reviewed by**: Almost nobody, per question — review happens on aggregate distributions
**Used for**:
- CI/CD: every PR or model swap triggers an automated run, score deltas gate merge
- Bulk regression detection
- Continuous monitoring across large input variation

The grading itself is done by "model-graded" evaluators — LLMs evaluating LLM
outputs against rubrics. **OpenAI Evals** has this as a first-class feature:
its `cot_classify` template (chain-of-thought then classify) is the default for
open-ended outputs, with concrete grader templates like `fact.yaml`,
`closedqa.yaml`, `battle.yaml` shipped in their registry.

- Repo: https://github.com/openai/evals
- Templates: https://github.com/openai/evals/blob/main/docs/eval-templates.md

The point of Layer 3 is not "is this one question right?" — it's **trends and
distributions across thousands of questions**. A 2% drop on 50,000 questions is
real signal even if any single question's ground truth is fuzzy.

---

## Layer 4 — Production logs

**Size**: continuous, ranges from thousands to billions per day
**Authored by**: real users (you don't write these — you observe them)
**Reviewed by**: automated classification + thumbs-up/down signals + sampled human review
**Used for**:
- The only ground truth that matters: did real users get value?
- Discovering query types that none of layers 1–3 anticipated
- Feeding back into Layer 1 (representative new patterns become hand-written
  golden examples in the next version)

Layer 4 is also the layer that **validates** Layers 1–3: if your offline
benchmarks improve but production thumbs-up rate doesn't, your benchmarks are
measuring the wrong thing.

---

## What "huge corpus" actually changes

When the document set grows from "10 books" to "millions of pages," three
practical shifts happen:

### Shift 1 — Stratified sampling, not full coverage

Industrial RAG over millions of documents doesn't try to write golden questions
covering every document. The standard pattern:

1. Classify documents by **type / importance / query frequency** (e.g. "API
   reference" vs "tutorial" vs "marketing page")
2. Sample 10–50 representative docs per stratum
3. Write Layer 1 against the representative set

For a 50,000-document legal corpus, that might mean Layer 1 is anchored to
~150 representative judgments across constitutional / contract / criminal /
administrative buckets — not 50,000 question-document pairs.

### Shift 2 — LLM-synthesized Layer 2 becomes essential

You can't hand-write enough questions to cover millions of documents. Layer 2
is no longer optional — it's the mechanism that gives broad coverage. The
proportion of effort shifts:

- 10-document personal project: 100% Layer 1, no Layer 2 needed
- 1,000-document team project: 80% Layer 1, 20% Layer 2 with audit
- Million-document enterprise: 5% Layer 1, 60% Layer 2, 35% Layer 3+4

### Shift 3 — Production logs become primary

For mature systems, Layer 4 dominates. Engineers read sampled user query logs
weekly, classify failures, and feed representative ones back into Layer 1.
The Layer 1 set effectively grows through real-user signal rather than
synthetic creativity.

The catch: **you only have Layer 4 after launch**. Pre-launch projects (like
this one) have to substitute hypothesis-driven Layer 1 work for it.

---

## Industrial case studies (what's verifiable, what's not)

I want to be honest about what's actually documented publicly vs. what's
common knowledge that lacks a clean citation. Verified claims with sources:

### HumanEval (the original code-eval benchmark)

Chen et al., "Evaluating Large Language Models Trained on Code,"
[arXiv:2107.03374](https://arxiv.org/abs/2107.03374). Introduced the
164-problem HumanEval benchmark and the Codex model that powers GitHub
Copilot. Codex solved 28.8% of HumanEval problems versus 0% for GPT-3.

Note: I claimed earlier that GitHub Copilot uses HumanEval-style automated
benchmarks for regression testing. I cannot verify that specifically from
public GitHub material. What I *can* verify is that HumanEval was introduced
alongside Codex (which powers Copilot). Whether they continue to use a
HumanEval-style suite for production gating is not publicly documented.

### Anthropic's red-teaming dataset

Ganguli et al., "Red Teaming Language Models to Reduce Harms,"
[arXiv:2209.07858](https://arxiv.org/abs/2209.07858). Anthropic publicly
released **38,961 red-team attacks** written by human red-teamers — a real
example of large-scale human-authored adversarial eval data.

The Constitutional AI paper ([arXiv:2212.08073](https://arxiv.org/abs/2212.08073))
extends this with LLM-generated training data via RLAIF, but the eval set
specifics are less cleanly documented in public sources than the red-team
dataset itself.

### Google Search Quality Rater Guidelines

[Public PDF](https://services.google.com/fh/files/misc/hsw-sqrg.pdf), linked
from Google's "How Search Works" page. Recent versions are around 170+ pages.
Used by Google's external "search quality raters" team — a real-world example
of human-authored reference standards at industrial scale, with a multi-hundred-
page operating manual for evaluators.

### Meta's LLaMA family

Public papers cover dozens of benchmarks across reasoning, QA, code, and
safety:
- LLaMA 1: [arXiv:2302.13971](https://arxiv.org/abs/2302.13971) — uses 20+
  benchmarks (PIQA, SIQA, HellaSwag, ARC, MMLU, GSM8K, HumanEval, etc.)
- LLaMA 2: [arXiv:2307.09288](https://arxiv.org/abs/2307.09288)
- LLaMA 3: [arXiv:2407.21783](https://arxiv.org/abs/2407.21783) — substantially
  expands the benchmark set

Concrete example of "evaluations are spread across many benchmarks, no single
one is authoritative."

### RAGAS testset generation

[Documentation](https://docs.ragas.io/en/latest/concepts/test_data_generation/rag/)
is the closest public-facing example of the Layer 2 pattern: knowledge-graph
nodes from your corpus → LLM-generated synthetic questions → samples include
`(user_input, reference_contexts, reference)`. Also offers `SingleHopQuery` and
`MultiHopQuery` synthesizers, recognizing that synthetic generation tends to
under-represent multi-hop questions unless explicitly forced.

### Claims I made that I could NOT verify

In an earlier conversation I made a few claims that turned out not to have
clean public sources:

- "Regulated industries require SME sign-off per question": the *spirit* is
  correct (FDA's Good Machine Learning Practice principles emphasize clinical
  expert involvement; EU AI Act requires conformance assessment), but I could
  not find a public regulatory document mandating "per-question" sign-off.
  Treat this as common practice in regulated AI development, not a specific
  citable rule.
- "5–20% spot-check rate for synthetic data": no major framework publishes
  this as a fixed standard. It's a heuristic that appears in practitioner
  blog posts, not in RAGAS / OpenAI / Anthropic documentation.
- "Eval pyramid" as a named industry concept: the building blocks (small
  curated + medium synthetic + large auto-graded + production logs) are real
  and described piecewise in framework docs, but no major framework calls
  this a "pyramid." It's my framing.

I want to flag these explicitly — overstated citations are an engineering
red flag in interviews, and "the broad pattern is widely practiced even
where formal documentation is sparse" is itself a credible observation.

---

## What this project should do

You're at the smallest possible scale: one corpus (1,151-page textbook),
one developer, no users yet.

| Stage | Action |
|---|---|
| **Now (Phase 1 prep)** | 100% Layer 1. Hand-write 30–50 golden questions. No Layer 2 yet. |
| **Phase 1 baseline** | Run Layer 1 against the deployed system. Establish baseline numbers. |
| **Phase 1 → Phase 2** | Add Layer 2: ~100 LLM-synthesized questions, audit 10–20 yourself. Use them as expanded coverage for the A/B comparison. |
| **Phase 2 final report** | Both layers used: Layer 1 for the headline numbers (because trustworthy), Layer 2 for breadth and statistical power. |
| **Hypothetical Layer 3+4** | Acknowledged in the final write-up as "what would be added if this were a real product with real users." |

The interview-grade insight: **knowing which layer you're in matters more than
having all four**. A small, clean Layer 1 plus an honest acknowledgment of the
absence of Layer 4 is far more credible than overstating coverage.

---

## Why this matters in interviews

Most candidates discussing RAG evals stop at "we used RAGAS" or "we hand-wrote
some questions." Engineers who can articulate the layered structure — what
each layer is for, where it comes from, what its blind spots are, and which
ones a particular project legitimately lacks — are visibly thinking about
eval as a system rather than a checklist.

The corollary: if you're asked "how would you scale this eval to a million-doc
corpus?", the answer is not "write more golden questions." The answer is
"shift the proportion of effort across the four layers, with Layer 1 anchored
to a stratified sample of representative documents."

---

## Takeaway

**Eval at scale is a portfolio of measurements, not a single measurement.**
Each layer answers a different question:

- Layer 1: *"On the cases experts care most about, are we right?"*
- Layer 2: *"On a representative spread of the corpus, are we right?"*
- Layer 3: *"At population scale, are we trending up or down?"*
- Layer 4: *"In the world of real users, do we work?"*

Skipping any layer doesn't break the system — it leaves a class of failures
invisible. The mature team knows which layers it has, which it lacks, and
why.

Companions:
- See `04-golden-set-design-playbook.md` for how to design Layer 1 well
- See `05-keyword-set-design.md` for how scoring within a layer interacts with
  this hierarchy
- See `01-rag-eval-strategy.md` for how the metrics within a layer are chosen
