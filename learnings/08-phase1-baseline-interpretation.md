# 08 — Phase 1 Baseline: When "Bad" Numbers Are the Point

**Date**: 2026-06-09
**Tags**: eval, phase1, baseline, two-phase-strategy, interpretation

## Question I started with
"I've deployed Phase 1 end-to-end — Vertex AI Search retrieving real OpenStax
content, Gemini 2.5 Flash generating real answers grounded in the context.
The eval harness ran successfully. But the numbers look... bad. Avg keyword
score 11.25%. Citation accuracy 0%. Did I do something wrong?"

## Short answer
The numbers are correct, and they're meaningful — but only as a *baseline*,
not as a final verdict. Each "failure mode" in the data corresponds to a
specific Phase 2 design decision. A Phase 1 that scored 90% would actually
*invalidate* the Phase 2 narrative: there'd be nothing left to improve. The
"bad" numbers are doing exactly what they were designed to do.

---

## The numbers, side by side

| Metric | Mock baseline | **Phase 1 baseline** |
|---|---|---|
| Avg keyword score | 19.79% | **11.25%** |
| Avg citation accuracy | 0.00% | **0.00%** |
| Avg latency (ms) | 1691 | **3044** |
| Per-bucket: factual | 15.00% | **18.00%** |
| Per-bucket: chapter_scoped | 33.33% | **0.00%** |
| Per-bucket: cross_topic | 16.67% | **0.00%** |
| Per-bucket: figure_or_diagram | 33.33% | **0.00%** |

Three counterintuitive observations that need explanation.

---

## Observation 1 — Phase 1 keyword score is *lower* than Mock

Mock generator returns templated text that happens to mention "Kepler",
"orbits", "Mars" frequently — high-frequency tokens from the OpenStax
fixture data. So a coincidental match score of ~20%.

Gemini 2.5 Flash, by contrast, **actually answers the question** — and
when it does, it answers tersely. astro-001 example:

> *"The provided text states that Kepler worked with 'the data for Mars'
> to analyze the motions of the planets [1]. However, it does not specify
> whose Mars observation data he used... [1]. Access for free at openstax.org"*

Hits "Mars" and "data" → 50%. Misses "Tycho Brahe" and "ellipse" → 50% lost.
But notice what's *correct* about this answer: **Gemini is being honest.**
It says "the text does not specify whose Mars observation data he used"
— because the single retrieved snippet really doesn't contain "Brahe."

The model is *more truthful* than mock; the eval metric is the same. The
score went down because the model stopped padding and only said what the
context supported.

This is actually a **win for faithfulness** — it just doesn't show up in a
keyword-substring metric.

### Lesson
Keyword scores measure *vocabulary overlap*, not *correctness*. A faithful
short answer can score lower than a hallucinated long answer. This is
exactly why Learning 05 emphasized that keyword is a *cheap pre-filter*,
not a verdict — and exactly why Phase 2 will add RAGAS faithfulness scoring
on top.

---

## Observation 2 — Citation accuracy is 0% across the board

Every `RetrievedChunk` in Phase 1 has `page = 1`, regardless of actual
source location. Golden set's `expected_page_ranges` are real PDF pages
(87, 95, 107, 920, etc.). Substring/range match is mathematically
guaranteed to fail.

**This is not a bug — it's a tier limitation.** Vertex AI Search Standard
tier:
- Returns document-level results, not chunk-level
- Doesn't include page numbers in result metadata
- Doesn't support extractive segments (which would expose `pageNumber`)

To get page numbers from Discovery Engine you'd need:
- Enterprise tier ($$$, plus extra fees per query)
- Or a self-built ingestion pipeline that splits the PDF into pre-paged
  chunks before import

Phase 1 was designed to deliberately not pay either of those costs. So
0% citation accuracy is the *expected* outcome — and is the single
strongest motivation for Phase 2 existing:

> *"Phase 2's Document AI Layout Parser + per-chunk page tracking will
> raise citation accuracy from 0% (literally cannot do it) to whatever
> the parser actually achieves."*

That's a story with concrete delta. It only works because Phase 1's number
is genuinely 0%.

---

## Observation 3 — Three buckets are 0% but `factual` is 18%

Per-bucket breakdown:

| Bucket | N | Phase 1 keyword |
|---|---|---|
| factual | 5 | 18.00% |
| chapter_scoped | 1 | 0.00% |
| cross_topic | 1 | 0.00% |
| figure_or_diagram | 1 | 0.00% |

Pattern: Phase 1 can do a *little* on factual (single-passage) questions,
but **completely fails** the harder buckets. Reasons by bucket:

### Why `chapter_scoped` is 0%
astro-004 needs Ch.3 §3.1 (Kepler's laws) + §3.3 (Newton's gravity) +
§3.5 (reformulation). Vertex AI Search returns only the single best
*document*-level match — never multiple chunks from different sections.
Gemini sees one snippet, can't synthesize across sections.

**Phase 2 fix**: chapter-aware chunking + retrieving top-k chunks lets
the LLM see all three sections at once.

### Why `cross_topic` is 0%
astro-006 needs Ch.5 (Doppler) + Ch.26 (Hubble). Same problem, more severe:
the two relevant passages are 700+ pages apart. Document-level retrieval
from a single 1,151-page PDF will pick whichever chapter is *most* relevant
— and lose the other.

**Phase 2 fix**: hybrid (BM25 + vector) retrieval with explicit per-chapter
filtering and book-scoping; LLM reranker keeps best from each topic.

### Why `figure_or_diagram` is 0%
astro-008 wants H-R diagram axes / creators. Standard tier doesn't
extract figures from PDFs. The text body around figures gets snippeted,
but figure captions and axis labels often don't surface as the top
result.

**Phase 2 fix**: Document AI Layout Parser pulls figure regions; Gemini
Vision generates captions; captions get embedded and retrieved alongside
text.

### Lesson
**Per-bucket reporting is what makes the data narrative possible.** A
single average ("Phase 1 = 11.25%") would be uninformative. The bucketed
view says "Phase 1 is okay-ish on the simple bucket and zero on every
bucket that maps to a Phase 2 design choice." That's a defensible story
for a job interview or a project writeup.

---

## What this baseline actually tells us

Three diagnoses, three Phase 2 prescriptions:

| Diagnosis | Evidence in baseline | Phase 2 prescription |
|---|---|---|
| **Retrieval surface too coarse** | astro-001: snippet missing "Tycho Brahe" because document-level snippet picks one passage out of 1,151 pages | Self-built pipeline with per-chunk indexing; hybrid BM25 (proper-noun friendly) + vector |
| **No page-level traceability** | All citations `page = 1` | Document AI Layout Parser → per-chunk `(page, bbox)` metadata |
| **Single-chapter bias** | All 3 multi-source buckets score 0% | Top-k retrieval + LLM reranker; structured chunk metadata enables cross-chapter joins |

These aren't speculative improvements. Each is targeted at a specific,
measured failure in the baseline.

---

## What a Phase 1 90% baseline would have meant

If the data had come back like this:

| Metric | Phase 1 (hypothetical good) |
|---|---|
| Avg keyword score | 90% |
| Avg citation accuracy | 85% |
| Per-bucket: all green |

That would actually be a *worse* outcome for the project. Reasons:

1. **No room for Phase 2 to demonstrate value.** Self-built RAG with
   pgvector + hybrid retrieval wouldn't have anything to win on.
2. **The two-phase narrative collapses.** "I built two systems, the second
   one is slightly faster, neither is meaningfully better" is not a
   compelling interview story.
3. **Probably means the eval set is too easy.** A managed product hitting
   85% citation accuracy on a corpus with no chunk-level metadata would
   be suspicious — likely the golden set was leaking signal somehow.

So one honest framing of Phase 1's purpose is: **demonstrate enough
capability to be a credible baseline; demonstrate enough failures to be
worth replacing.** Both happened.

---

## Latency: 3044 ms (Phase 1) vs 1691 ms (Mock)

Phase 1 is ~1.8× slower. Breakdown of the additional time:

- Vertex AI Search round-trip: ~500-800 ms
- Gemini 2.5 Flash generation (real, not mocked): ~1500-2500 ms
- gRPC connection setup, serialization, etc.: ~200-300 ms

Mock generator was synthetic streaming with artificial 50-100 ms
per-token delay, totaling 1.7s — not real model latency. Phase 1's
3 seconds is realistic for a true RAG system.

For comparison, Phase 2 is *expected* to add ~1-2 seconds of latency
(LLM reranker pass) but improve quality. The latency tradeoff is part
of the A/B story, not a regression.

---

## Cost so far

After full Phase 1 deployment + 8-question eval run:

- Datastore + engine creation: free
- One-time PDF indexing (1,151 pages, Standard tier): ~$2-3
- 8 search queries: ~$0.02 (Standard tier per-query is cheap)
- 8 Gemini 2.5 Flash calls: ~$0.05 (averaging 200 input + 100 output tokens)

**Total real spend: under $5 USD**, comfortably within the ¥2,000 budget alert.

A full Phase 1 baseline run (the headline number) costs less than a coffee.

---

## What's interview-worthy here

### The narrative shape

> "I designed Phase 1 with the explicit hypothesis that managed Vertex AI
> Search would underperform on three specific failure modes — coarse
> retrieval surface, no page-level traceability, and single-chapter bias.
> The baseline data confirms this: 0% citation accuracy under Standard
> tier, 0% on all three multi-source buckets. Phase 2's pgvector +
> Document AI + hybrid retrieval pipeline targets exactly those three
> failure modes. The data tells me what to build, not the other way
> around."

### The reading-the-numbers skill

The 11.25% keyword score includes *better* answers than mock, scored *worse*
because the model stopped hallucinating padding. Knowing to look at this
distinction is the difference between "score went down, panic" and "score
went down, system improved." This kind of skeptical-but-honest interpretation
is the interview-grade signal.

### The "I would expect a high baseline to be a red flag" insight

If asked "what would you do differently if Phase 1 baseline came back at 90%?"
— the honest answer is "I'd suspect the eval set." That's not pessimism;
it's calibration. A managed search product hitting 90% on a realistic eval
would imply the eval was leaking ground-truth signals into the input. The
ability to reason about this is rare.

---

## A real follow-on: the over-refusal pattern, and what prompt tuning could (and couldn't) fix

After publishing the first baseline, I tested several golden questions
manually in the web UI and noticed something the eval harness numbers had
hidden: **most questions came back with "I don't find this in the sources"**,
even when the retrieved snippet actually contained relevant information.

### The diagnosis

Inspecting four representative questions side-by-side:

| Question | Retrieved snippet | Gemini's answer (original prompt) |
|---|---|---|
| Kepler's Mars data source | "Working with the data for Mars..." (truncated) | ❌ "I don't find this in the sources." |
| Newton's gravity insight | Direct, complete passage about Moon | ✅ Correct partial answer |
| How was Neptune discovered? | Snippet starts with "The Discovery of Neptune..." | ❌ "I don't find this in the sources." |
| Slipher's spiral spectra | Off-topic — landed on Ch.5 sodium emission spectrum | ❌ "I don't find this in the sources." (correctly!) |

This is **two independent problems stacking**:

**Problem 1 — Snippet-density problem (retrieval layer).**
Standard tier returns ~200-character highlight snippets, often with `...`
elision joining non-contiguous fragments. Gemini sees "Working with the data
for Mars" but never sees the preceding "used Tycho Brahe's data" — so it
honestly says "the source doesn't say." Faithfulness is working *too well*.

**Problem 2 — Retrieval miss (ranking layer).**
The Slipher question got document-level snippets matching "pattern + spectrum"
in Ch.5 (about sodium emission), totally missing Ch.26 (Slipher's actual
discovery). Gemini's refusal here is *correct* — the retrieved context
genuinely doesn't have the answer.

### What's fixable now (prompt) vs what's not (retrieval)

| Layer | Problem | Fixable in Phase 1? |
|---|---|---|
| Generation | Over-refusing when partial info exists | ✅ Prompt tuning |
| Retrieval | Snippet too short, no context window | ❌ Standard tier limitation |
| Ranking | Wrong document/section returned | ❌ Document-level retrieval limit |
| Citation | Page numbers absent | ❌ Tier limitation |

Only the first row is reachable without changing infrastructure. So I
rewrote the system prompt around a **three-mode response framework**:

```
MODE A — Full answer. The context fully answers the question.
MODE B — Partial answer. The context answers part of the question.
         Share what IS in the context [n], then explicitly state what
         specific part is NOT in the provided sources.
MODE C — Not found. The context contains no relevant information.
         Say "I don't find this..." AND briefly describe what topic
         the retrieved context DID cover, so the user knows retrieval
         may have missed.

Strict rule: prefer Mode B over Mode C when the context is even
partially relevant — users prefer a partial answer that names its
limits over a flat refusal.
```

### Real before/after on the same questions

| Question | Original prompt | Tuned prompt |
|---|---|---|
| Kepler's Mars data source | "I don't find this..." | **"The context states Kepler worked with the data for Mars [1], but does not specify whose observation data he used."** |
| How was Neptune discovered? | "I don't find this..." | **"The context states Neptune was discovered as the eighth planet [1]. However, it does not specify the method or process by which Neptune was discovered."** |
| Slipher's spiral spectra | "I don't find this..." | **"I don't find this in the sources. The provided context discusses general concepts of emission spectra and patterns [1]."** |

The third example is especially valuable — Gemini doesn't just refuse, it
**tells the user the retrieval missed**. The user now knows to rephrase or
broaden the query, not assume the textbook lacks the answer.

### Quantitative impact on the baseline

Re-running the full eval harness with the tuned prompt (no retrieval changes):

| Metric | Original prompt | **Tuned prompt** | Δ |
|---|---|---|---|
| Overall keyword score | 11.25% | **18.54%** | +65% |
| Factual bucket | 18.00% | **23.00%** | +28% |
| Chapter_scoped bucket | 0.00% | **16.67%** | from-zero |
| Cross_topic bucket | 0.00% | **16.67%** | from-zero |
| Figure_or_diagram bucket | 0.00% | 0.00% | unchanged |
| Citation accuracy | 0.00% | 0.00% | unchanged |

Two observations:

**1. The two "dead" buckets came back to life.** chapter_scoped and
cross_topic went from 0% (flat refusal) to 16.67% (partial answers with
named gaps). This is real signal — the system is now communicating *what
it knows* rather than going silent the moment it doesn't know everything.

**2. Figure_or_diagram and citation accuracy stayed at 0%.** No prompt
change can recover information the retriever didn't fetch in the first
place. These two metrics confirm the limits of prompt-layer fixes.

### Console-side smoke test: structural noise in retrieved snippets

After tuning the prompt, I went into the Vertex AI Search Console **Preview**
tab to spot-check retrieval quality directly (bypassing our FastAPI). Two
queries exposed a problem I hadn't named yet:

| Query | Top snippet returned by Vertex AI Search |
|---|---|
| `Hertzsprung Russell diagram` | "**Diagram** 609 Key Terms..." |
| `Slipher spiral nebulae redshift` | "We'll be discussing these 'death shroud' **nebulae** in Further Evolution of Stars. (b) Stephan's Quintet..." |

Both results are real text from the PDF. Both are also **structurally
useless** for answering the user's question:

- The H-R query landed on the **end-of-chapter Key Terms list**, not the
  body text in §18.4 that actually explains the diagram.
- The Slipher query landed on a **figure caption** about Stephan's Quintet,
  100% unrelated to Slipher's spectral observations.

### Why this happens

Standard-tier Vertex AI Search treats the entire 1,151-page textbook as
**one document** for retrieval. Inside that document, all of these are
just text:

- Body paragraphs (the actual explanations) ✅ what we want
- Section headings
- Figure captions
- End-of-chapter Key Terms lists (glossary-style)
- Chapter Summaries
- Review/Exercise questions
- Appendices and indexes

The retriever **doesn't know which of these is "explanatory text" vs
"structural metadata."** Worse, terse glossary lines and figure captions
*often score higher* on keyword/embedding similarity for short queries
than long expository prose, because the keyword density is concentrated.

A user asking "what is the H-R diagram?" should hit §18.4's explanation
("In 1913, Henry Norris Russell plotted the luminosities of stars against
their spectral classes..."). Instead they get an entry from the Key Terms
list saying essentially "H-R diagram → see definition." That's not a
retrieval bug; that's a **chunking + structure-awareness bug**.

### What this adds to the Phase 2 case

The two-phase narrative now has a third concrete failure mode the prompt
tuning section couldn't name:

| Failure | Layer | Phase 2 fix |
|---|---|---|
| Over-refusal on partial info | Generation | ✅ Prompt tuning (already done) |
| Document-level retrieval can't span chapters | Retrieval | ✅ Per-chunk indexing |
| Standard tier returns no page metadata | Tier limit | ✅ Document AI Layout Parser |
| **Structural noise: Key Terms / figure captions outrank body text** | **Chunking + structure** | ✅ **Document AI block-type filtering** |

Phase 2's Document AI Layout Parser exposes a `layoutType` per block — values
like `body-text`, `heading-1`, `caption`, `list-item`, `table`. The Phase 2
ingestion pipeline can then:

1. **Filter or down-weight** non-body-text blocks (Key Terms, figure
   captions, exercise questions) at index time
2. **Tag chunks with their block type** so retrieval can prefer body text
   for explanation queries and only return captions when the query is
   explicitly about a figure

Phase 1's Vertex AI Search Standard tier has no such block-type signal —
it sees a flat stream of text. This is genuinely structural; no prompt
or query reformulation can fix it.

### How to do this Console-side smoke test yourself

1. Open the engine page (Console → AI Applications → Engines)
2. Click the engine → **Preview** tab
3. Type queries that should hit specific sections (e.g. "Kepler's third law")
4. Inspect the **first** snippet returned
5. Look for the structural-noise pattern:
   - Snippet starts mid-sentence with `...`
   - Snippet contains "Key Terms", "Summary", "Figure X.Y", "Exercises"
   - Snippet is suspiciously short or fragmentary

Each of those indicates structural-noise overranking. **Document this when
you find it** — it's the most concrete evidence for "managed retrieval
isn't structure-aware enough for textbook-style content," and it tells
your Phase 2 ingestion design exactly what block types to filter.

---

### Why this matters for the two-phase narrative

The instinct "low scores → improve the prompt" is half right and half
wrong. Knowing **which low scores prompt-tuning can move** and which it
cannot is the actual skill. After this round:

| Issue | Prompt tuning helped? | What it actually means |
|---|---|---|
| Over-refusal on questions with partial context | ✅ +65% overall | Generation-layer problem, prompt-fixable |
| Wrong document retrieved entirely | ❌ unchanged | Retrieval-layer problem, needs Phase 2 |
| No page numbers in citations | ❌ unchanged | Tier limitation, needs Phase 2's Document AI |
| Multi-section synthesis (chapter_scoped) | ⚠️ partial — answers exist now but limited by snippet | Retrieval-layer problem partially compensated |

This sharpens the Phase 2 case: **prompt tuning got us all the easy wins.
Everything that's still 0% is a structural retrieval limitation, not a
generation problem.** Phase 2's hybrid retrieval + Document AI parsing
+ chunk-level page tracking maps directly onto exactly the metrics that
didn't move with prompt tuning.

### Interview takeaway

> *"After deployment I found the system was over-refusing — Gemini saying
> 'I don't find this' even when retrieval had partial info. I diagnosed
> this as a prompt-level problem (binary 'answer or refuse') stacked on
> top of a retrieval-level problem (Standard-tier snippets being too
> truncated). I split the prompt into three response modes — full,
> partial-with-named-gaps, and not-found-with-context-summary. The result
> was +65% on overall keyword score and reviving two dead buckets. But
> figure_or_diagram and citation accuracy stayed at 0% — those are
> retrieval limits, not prompt limits. Knowing which knob fixes which
> problem is what made this useful instead of being a guess-and-check
> session."*

---

## Concrete numbers to remember

For the project writeup / interview / PR description:

```
Phase 1 baseline (Vertex AI Search Standard + Gemini 2.5 Flash):
- Keyword score: 11.25% overall, 18% on factual, 0% on multi-source buckets
- Citation accuracy: 0% (Standard tier returns no page metadata — by design)
- Latency: 3044 ms p50
- Cost: ~$5 USD for full deployment + first eval run

Three documented failure modes feeding Phase 2 design:
- Document-level retrieval (no chunks) → Phase 2 self-built chunking
- No page numbers under Standard tier → Phase 2 Document AI Layout Parser
- Single-chapter bias → Phase 2 hybrid retrieval + LLM reranker
```

---

## Takeaway

**A baseline is not a verdict; it's a measurement.** The numbers say
exactly what Phase 1 was designed to say: a managed RAG product is
serviceable on simple questions and broken on hard ones. That measurement
is the foundation Phase 2 will be A/B-compared against.

The interview version:

> *"My Phase 1 baseline scored 11% on keywords and 0% on citation accuracy.
> That sounds bad until you read what's behind it: Standard-tier Vertex AI
> Search literally cannot return page numbers, and document-level retrieval
> can't synthesize across chapters. Each failure mode maps to a specific
> Phase 2 design decision. The 'bad' numbers are the substrate the rest
> of the project is built on."*

Companions:
- See `01-rag-eval-strategy.md` for why we use bucketed reporting at all
- See `02-eval-before-deploy.md` for why these baseline numbers had to be
  defined *before* deployment
- See `07-vertex-ai-search-setup.md` for the deployment work that produced
  these numbers, including the Standard-tier limitations
