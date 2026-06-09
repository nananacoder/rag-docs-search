# 05 — Designing `expected_answer_keywords`: Synonyms, OR-relations, and the Real Purpose

**Date**: 2026-05-25
**Tags**: eval, golden-set, scoring, schema-design

## Question I started with
"While auditing astro-001 against the source pages, I needed to decide between
`["Brahe", "Mars", "data", "ellipse"]` and
`["Brahe", "Mars", "data", "observations", "ellipse"]`. They look almost
identical. Does it matter? What's the actual decision rule?"

## Short answer
Keyword sets are a **cheap pre-screen**, not the final judgment. The real rules
are: (1) every keyword must be **independently necessary** in a correct answer,
(2) **synonyms break that rule** because the system can satisfy the meaning
without using the specific word, (3) when two synonyms are both valid, pick
the higher-frequency one in the corpus or drop the keyword entirely. Don't add
both: that doesn't make scoring stricter, it makes it punish verbosity.

---

## How `expected_answer_keywords` actually scores

A typical eval harness implementation:

```python
def keyword_score(answer: str, expected_keywords: list[str]) -> float:
    matches = sum(1 for kw in expected_keywords if kw.lower() in answer.lower())
    return matches / len(expected_keywords)
```

**Implication**: every keyword in the list is an **independent AND** that the
system must satisfy. Adding more keywords raises the bar, regardless of whether
they overlap in meaning.

## The synonym trap

Consider the question:
> *"Whose Mars data did Kepler use to discover elliptical orbits?"*

A correct system answer might be:
- "Kepler used **Brahe's data** for **Mars** to discover the **elliptical** orbits..."  ← uses "data"
- "Kepler analyzed **Brahe's observations** of **Mars** and discovered an **ellipse**..."  ← uses "observations"

Both answers are correct. But:

| Keyword set | Answer A (uses "data") | Answer B (uses "observations") |
|---|---|---|
| `["Brahe", "Mars", "data", "ellipse"]` | ✅ 4/4 | ❌ 3/4 |
| `["Brahe", "Mars", "data", "observations", "ellipse"]` | ❌ 4/5 | ❌ 4/5 |
| `["Brahe", "Mars", "ellipse"]` | ✅ 3/3 | ✅ 3/3 |

**Adding "observations" alongside "data" doesn't make the system prove more —
it forces the system to use *both phrasings*, which is wordy, not correct.**

## The decision rule

For each candidate keyword, ask: **"Is this word something a correct answer
*must* contain, with no acceptable substitute?"**

| Word in question | Verdict |
|---|---|
| `Brahe` | ✅ Yes — proper name, no substitute |
| `Mars` | ✅ Yes — specific planet matters |
| `ellipse` | ✅ Yes — core concept word |
| `data` | ⚠️ Maybe — but "observations" or "records" are equivalent |
| `observations` | ⚠️ Maybe — but "data" or "records" are equivalent |
| `discovered` | ❌ No — could say "found", "realized", "showed", etc. |
| `Tycho` | ⚠️ "Brahe" alone usually identifies him; "Tycho Brahe" is more precise |

The "must contain" filter eliminates verbs and connector words quickly. It
exposes synonyms — words where multiple variants would be equally correct.
Those are the hard cases.

## Three ways to handle synonym pairs

### Option A — Pick the higher-frequency one
Look at how the corpus phrases it. The OpenStax text uses "Brahe's data" more
often than "Brahe's observations", so a system retrieving from the corpus is
more likely to surface "data" in its answer.

```json
"expected_answer_keywords": ["Tycho Brahe", "Mars", "data", "ellipse"]
```

**Trade-off**: a system that answers correctly using "observations" instead
of "data" gets a false-negative on this keyword. Acceptable because keyword
matching is a coarse filter, not the final score.

### Option B — Drop the ambiguous keyword
If you can't pick a clear winner, omit the keyword entirely:

```json
"expected_answer_keywords": ["Tycho Brahe", "Mars", "ellipse"]
```

**Trade-off**: looser pre-screen, more answers pass; you rely more heavily
on RAGAS / LLM-judge for the real verdict.

### Option C — Upgrade the schema to support OR-groups
Industry-grade harnesses use nested structure:

```json
"expected_answer_keywords": [
  "Tycho Brahe",
  "Mars",
  ["data", "observations", "records"],
  "ellipse"
]
```

Scoring logic: top-level entry that is a string → substring match; entry that
is a list → any-match counts as one hit.

**Trade-off**: harness gets more complex; schema migrations are required when
eval tooling updates. For v1, not worth the engineering cost.

### In this project
Chose **Option A** for astro-001 (`data` over `observations`). Reasoning:
- v1 schema is intentionally minimal — flat list of strings, fastest to write
  and easiest for harness to consume
- The corpus phrasing favors "data", so retrieval-grounded answers are more
  likely to contain that word
- If post-hoc analysis shows several questions getting false-negatives because
  of synonym mismatch, v2 schema will introduce OR-groups (Option C)

This is a deliberate decision to **start with the simplest schema that works
and graduate to richer schemas only when data justifies it.** The opposite
mistake — designing the perfect schema before any eval runs exist — is
classic over-engineering.

---

## The deeper point: keyword scoring is not the final judgment

`expected_answer_keywords` is a **cheap pre-screen**. Its job is to flag
obviously-wrong answers fast:
- Answer doesn't mention "Brahe"? Almost certainly wrong.
- Answer mentions all 4 keywords? Probably on track — but still gets evaluated
  by other metrics.

The actual answer-quality metrics live elsewhere:

| Metric | What it measures | Fooled by keywords? |
|---|---|---|
| **Keyword score** | Does the answer mention the right words? | N/A — this *is* the keyword check |
| **RAGAS Faithfulness** | Is the answer grounded in the retrieved context (no hallucination)? | No — this catches "uses keywords but invents facts" |
| **RAGAS Answer Relevance** | Does the answer actually address the question? | No — this catches "uses keywords but answers a different question" |
| **Citation Accuracy** | Are the cited pages correct? | No — this is independent |
| **LLM-judge holistic** | Would a domain expert call this correct? | No — most expensive but most accurate |

A **good** answer scores well on all of them. A **suspicious** answer scores
high on keywords but low on faithfulness — meaning it parroted the right words
without true grounding. This pattern is exactly why keyword scoring alone
isn't enough.

So when designing keywords:
- **Don't try to make keywords carry too much weight.** Keep them as the
  cheap first filter.
- **Don't try to encode every nuance into keywords.** Let RAGAS and LLM-judge
  catch the subtleties.
- **Don't punish verbosity by stuffing the list with synonyms.** That confuses
  "answer is correct" with "answer used my preferred phrasing."

---

## The two dimensions of "leniency"

A natural follow-up question: **"If I want my eval to be more lenient, do I just
shorten the keyword list?"** The answer is more nuanced than yes/no — leniency
isn't one dial, it's two.

### Dimension 1 — Absolute threshold leniency
**Fewer keywords ⇒ easier to pass overall.** With 3 keywords a system answer
that nails the core ideas will pass; with 6 keywords the same answer might
miss one edge concept and fall below threshold.

### Dimension 2 — Per-miss penalty leniency
**More keywords ⇒ smaller penalty for missing any single one.**

Concrete numbers (assuming a perfect answer hits every keyword):

| Keyword count | Score when 1 is missed | Penalty per miss |
|---|---|---|
| 3 | 2/3 = 0.67 | -33% |
| 4 | 3/4 = 0.75 | -25% |
| 5 | 4/5 = 0.80 | -20% |
| 6 | 5/6 = 0.83 | -17% |
| 10 | 9/10 = 0.90 | -10% |

So "more keywords" makes each individual word matter *less* — but introduces
*more* opportunities to miss something. These two effects cut in opposite
directions, which is why "fewer = lenient" is too simple.

### A worked example: the same question, three keyword sets

For *"What was Newton's central insight..."*:

| Answer scenario | 4-kw `[universal, Moon, inverse square, all bodies]` | 5-kw `[+ apple]` | 3-kw `[universal, Moon, all bodies]` |
|---|---|---|---|
| Perfect answer (all hit) | 1.00 | 1.00 | 1.00 |
| Correct, omits "apple" | 1.00 ✅ | 0.80 ⚠️ | 1.00 ✅ |
| Correct, expresses inverse-square as "1/r²" | 0.75 ⚠️ | 0.80 ⚠️ | 1.00 ✅ |
| Wrong / off-topic | 0.25 | 0.20 | 0.33 |

Notice three things:
1. The 3-keyword set is most forgiving on *good* answers — but also lets a
   wrong answer score 0.33, which is only slightly worse than a partial-credit
   correct one
2. The 5-keyword set is harshest on the "missing apple" case but actually
   *more lenient* than the 4-keyword set on "missing inverse square"
3. The 4-keyword set is the engineered middle: requires real conceptual
   coverage without punishing optional vocabulary

### What "leniency" really should mean

The honest framing: **don't tune leniency by keyword count.** That introduces
phrasing artifacts. Tune leniency by:

- **Lowering the score threshold** for "passing" (e.g., require ≥ 0.6 instead of ≥ 0.8)
- **Lowering the keyword score's weight in the composite metric** (e.g., final = 0.3·keyword + 0.5·RAGAS + 0.2·citation)
- **Using OR-groups** (Option C from earlier) when synonyms are genuinely interchangeable
- **Adding a negative-keyword set** when you want strictness (forbidden words must NOT appear)

Adjusting the keyword *list* should be about **correctness** (does this word
truly belong?) not about **strictness tuning**. Keep those two design knobs
separate, or you'll find yourself fighting one with the other.

### In this project
Decided on **4 keywords** for astro-003: `["universal", "Moon", "inverse square", "all bodies"]`.
The decision was driven by the "must-appear" rule (apple is narrative
flourish, not core), **not** by a desire to be more lenient. If at eval time
the threshold turns out to be wrong, the fix will be threshold tuning or
metric reweighting — not keyword count gymnastics.

---

## How major RAG / LLM-eval frameworks actually handle this

Surveying RAGAS, TruLens, DeepEval, OpenAI Evals, Anthropic's docs, LangSmith,
Phoenix (Arize), and Vertex AI's eval guidance reveals a clear pattern:

### Status of keyword scoring

| Framework | Keyword/substring as first-class? | Stance |
|---|---|---|
| **OpenAI Evals** | ✅ Yes — three graders: `Match` (prefix), `Includes` (substring), `FuzzyMatch` (bidirectional) | Pragmatic; "academic benchmarks fit this mold" |
| **Anthropic** | ✅ Yes — explicitly recommended | "Code-based grading is fastest, most reliable, extremely scalable" — preferred over LLM-judge when possible |
| **LangSmith** | ✅ Yes — "specific keywords" listed as quality heuristic | Co-equal with LLM-judge in 4-category framework |
| **Phoenix (Arize)** | ✅ Yes — "deterministic code-based evaluators" | First-class peer to LLM-judge |
| **Vertex AI** | ⚠️ Available via "computation-based metrics" (BLEU/ROUGE) | Pushes "adaptive rubrics" as recommended path |
| **RAGAS** | ⚠️ Yes but second-tier — `ExactMatch`, `StringPresence` | Core RAG metrics are LLM-judge; string metrics for tool-calls |
| **TruLens** | ❌ Not surfaced | Calls traditional NLP "too syntactic"; ladder skips keyword entirely |
| **DeepEval** | ❌ Almost none | "Almost all predefined metrics use LLM-as-a-judge"; scorers undocumented |

### Leniency mechanics — surprisingly primitive everywhere

**Not a single major framework has a rich keyword DSL.** The standard pattern is:
- List of strings
- `any(b in a for b in B)` — substring containment, OR across the list
- Sometimes whitespace/case normalization (Anthropic explicit)

Nobody publicly ships:
- Required-vs-optional keyword groups
- Weighted keywords
- Built-in synonym dictionaries
- Soft-OR thresholds (e.g. "match ≥ 3 of these 5")

OpenAI Evals' `Match` / `Includes` / `FuzzyMatch` three-tier ladder is the
most differentiated leniency design publicly documented, and it's still just
substring containment with different orientations.

### Stated philosophies on the keyword vs LLM-judge balance

- **Anthropic**: code-based grading first, human second, LLM third. Volume of
  cheap-graded cases beats fewer hand-graded ones.
- **DeepEval**: explicitly opposite — "scorers underperform for tasks
  requiring reasoning"; nearly everything is LLM-judge.
- **TruLens**: traditional NLP isn't even on the recommended ladder; medium
  LMs (BERT-class) are the "sweet spot," and LLM-judges agree with humans at
  high rates.
- **RAGAS**: keyword metrics exist for narrow uses (tool-call argument
  matching). Open-ended QA is LLM-judge territory.
- **Vertex AI**: "adaptive rubrics" (LLM-generated per-prompt unit tests) are
  the recommended path. Computation-based fallback only when ground truth exists.

### Industry trend

Three converging patterns:

1. **Keyword scoring is not dying — it's being demoted from "primary" to
   "fast pre-filter / narrow-task tool."** Most frameworks keep it as a
   first-class option but explicitly tell you it's not the right tool for
   open-ended prose.

2. **Hybrid is the default.** Almost every framework gives keyword and
   LLM-judge co-equal status. DeepEval is the outlier going nearly pure
   LLM-judge.

3. **The frontier is rubrics, not richer keyword DSLs.** Vertex AI's
   adaptive rubrics, DeepEval's G-Eval and DAG, RAGAS's increasing reliance
   on LLM-judge — all represent a vote that *if you need leniency mechanics
   richer than substring containment, switch to a structured LLM rubric*
   rather than build a more elaborate keyword grammar.

### What this means for your design

If you find yourself wanting "richer keyword logic" — required vs optional,
weighted, synonym-aware — that's a signal you've outgrown keyword scoring,
not a signal that you need a better keyword schema. The industry consensus
is to **promote that question to an LLM-judge with a clear rubric** rather
than try to encode the nuance into the substring-matching layer.

For this project: keyword stays as the cheap pre-filter, LLM-judge / RAGAS
carries the nuance. The schema stays a flat list of strings. If real eval
runs reveal that several questions need synonym handling, the upgrade path
is **LLM-judge for those questions**, not OR-groups in the schema.

---

## Practical heuristic for keyword set size

For typical RAG eval questions:
- **3–6 keywords** is the right range
- Below 3 → too lax, almost everything passes
- Above 6 → either redundant synonyms or stuffing in non-essential words

If you find yourself wanting more than 6, that's a signal the question is
either too compound (split it into two) or you're trying to use keywords for
something they're not designed for (use RAGAS / LLM-judge instead).

---

## Audit checklist for `expected_answer_keywords`

Before committing each entry:

```
[ ] Every keyword is independently necessary (not a synonym of another)
[ ] No keyword is a verb that has natural alternatives (said/showed/found/etc.)
[ ] Keyword count is between 3 and 6
[ ] Each keyword survives the "could this be phrased differently?" test
[ ] Proper nouns are present in the form most likely to appear in the corpus
    (e.g. "Tycho Brahe" not just "Tycho", if the corpus uses the full name)
```

---

## Takeaway

**Keyword sets are a coarse pre-screen, not a verdict. Design them to be
robust to phrasing — not to enforce a specific phrasing.** The interview-version:

> *"I treat `expected_answer_keywords` as a cheap pre-filter for obviously-wrong
> answers, paired with faithfulness and relevance metrics that catch the
> nuances. The biggest design mistake is stuffing synonyms in to feel
> 'thorough' — that just punishes verbose-but-correct answers. The right
> question to ask of every keyword is 'is this word something a correct
> answer must contain, with no acceptable substitute?' If the answer is no,
> drop it."*

Companions:
- See `04-golden-set-design-playbook.md` for the broader schema design rationale.
- See `01-rag-eval-strategy.md` for how keyword scoring fits with RAGAS metrics.
