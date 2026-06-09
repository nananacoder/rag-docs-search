# 04 — Golden Set Design Playbook: How to Build the "Reference Truth"

**Date**: 2026-05-25
**Tags**: eval, golden-set, methodology, governance

## Question I started with
"How do you actually create the questions and answers that an eval set is
built on? Is it just one person hand-writing them? In a real industry setting,
who owns this? What's the right JSON schema, the right size, how do you
*decide* this is your reference standard, and how do you audit it?"

## Short answer
A golden set is not a "test" — it is the **operational definition** of what
"correct" means for the system. Designing it is a governance exercise as much
as an engineering one. Six interlocking decisions (who writes, how many,
what schema, who signs off, how it stays current, how it's audited) shape
whether the eval has any meaning at all. None of them have universal
right answers — but each has a defensible decision framework.

---

## Decision 1 — Who writes the questions?

### The four sources, and their tradeoffs

| Source | Cost | Quality signal | Bias risk |
|---|---|---|---|
| **Hand-written by domain expert** | High (hours/question) | Highest — reflects actual user intent | Low — but limited diversity |
| **Hand-written by engineer reading the corpus** | Medium | Good for portfolio / small projects | Skewed toward "easy to extract" patterns |
| **LLM-synthesized then human-filtered** | Low–medium | Decent at scale | Echoes LLM biases; favors patterns the LLM can already answer |
| **Mined from real user logs** | Low (once you have logs) | Highest authenticity | Survivorship bias; only exists post-launch |

### The deeper rule
**Whoever writes the question must not be the system you're evaluating.** This
sounds obvious but is often violated:

- Synthesizing questions with the same LLM you use for generation = circular eval
- Letting the retrieval system "suggest" questions = retrieval can't be wrong about itself
- Auto-generating questions from chunks = the eval favors chunks that survived chunking, ignoring what was lost

A good rule of thumb: the question source should have **at least one independent
mental model of the corpus** that the system being evaluated does not have.

### Industry patterns

| Setting | Who writes |
|---|---|
| **Pre-launch (no user data)** | Domain expert + product manager + ML engineer in 3-way review |
| **Mature product** | Mix: real user query logs (sampled, anonymized, classified) + curated edge cases written by engineers |
| **Regulated industry (legal, medical)** | Subject-matter expert writes; engineer cannot author. SME signs off in writing |
| **Personal / portfolio** | Engineer hand-writes, ideally consulting at least one external reference |
| **Crowd-sourced products** | Mechanical Turk-style crowd writes; senior reviewer audits 10% |

### In this project
**Engineer (me) hand-writes against OpenStax Astronomy 2e.** Three reasons:
1. Single-author projects don't have separate roles to assign
2. The corpus is a textbook with explicit Review Questions written by domain
   experts (Fraknoi/Morrison/Wolff) — I'm starting from those rather than
   inventing from scratch, which gives independent provenance
3. Hand-writing forces familiarity with the corpus, which pays off later when
   tuning chunking, prompts, and bucket design

**What I deliberately avoided:** synthesizing questions with Gemini against
the same corpus, even though it would be 10× faster. That eval would tell me
"this Gemini agrees with Gemini" and nothing else.

---

## Decision 2 — How many questions?

### The shape of the tradeoff

| Size | When to use | Pros | Cons |
|---|---|---|---|
| **5–15** | Smoke test, sanity check | Free, fast | Statistically meaningless; one bad question dominates |
| **30–50** | Per-bucket averages stable | Manageable to write | Confidence intervals still wide |
| **100–300** | Per-bucket × per-segment cross-tabs | Real statistical power | Days of human work |
| **1,000+** | Production benchmark, regression suite | Distinguishes 1–2% changes | Days to weeks; usually requires synthetic + filter |
| **10,000+** | Foundation model benchmarks (TREC, BEIR) | Industry baseline | Only for shared benchmarks, not project-specific |

### The signal-to-noise calculus

For per-bucket reporting, you need **at least ~10 questions per bucket** before
the average means anything. With 4 buckets that's a floor of 40. With confidence
intervals you'd want 25/bucket → 100. So:

- **30–50** is the "you can report bucket averages without lying" floor
- **100+** is the "you can detect a 5% delta between Phase 1 and Phase 2" range
- **<20** is "vibes-only"

### The hidden cost: maintenance
Every question is a liability that must be maintained:
- Corpus updates may invalidate `expected_page_range`
- Model upgrades may change which keywords appear in the answer
- Bucket definitions evolve, recategorizing old questions

**Doubling the eval set roughly doubles the maintenance debt.** This is why
mature systems often *shrink* their golden sets to a curated core, not grow them.

### In this project
**Target: 30–50 questions for v1.** Currently at 8 (starter). Justification:
- 4 buckets × ~10 questions = 40 — meets the per-bucket floor
- Manageable to write in 4–6 sessions
- Phase 1 vs Phase 2 A/B needs detectable deltas, not 1% precision
- Can grow to 100 in v2 once Phase 1 baseline numbers identify which buckets need more questions

---

## Decision 3 — What's the schema?

### The four field categories

Every golden entry has fields from these four groups, in roughly this order
of necessity:

**Identity** — make the entry referenceable
- `qid` — stable identifier (don't reuse, don't renumber)

**Question** — what the system is asked
- `question` — natural-language prompt
- (optional) `query_type` / `bucket` / `tags` — for sliced reporting

**Expected answer** — what defines "correct"
- `expected_answer_keywords` — substrings that must appear (cheap, robust)
- (optional) `expected_answer_text` — full reference answer (used by LLM-judge)
- (optional) `expected_answer_constraints` — negative constraints ("must NOT say X")

**Expected source** — where the answer should come from
- `expected_book` / `expected_chapter` / `expected_page_range` — citation ground truth
- (optional) `expected_chunk_ids` — stricter retrieval ground truth

### The schema-design rule
**Add a field only if at least one metric uses it for scoring, OR if a human
reviewer needs it.** Speculative fields rot. Examples:

- `difficulty_level` (easy/medium/hard) — useless unless you slice reports by it
- `created_by` — useful in industry (audit), useless solo
- `last_verified_date` — critical at scale, overhead solo
- `expected_chunk_ids` — only useful if you have stable chunk_ids, which means corpus
  is already indexed → impossible to write before deployment

### Industry-grade schemas typically add

| Field | Why |
|---|---|
| `created_by` | Audit trail — who authored this |
| `reviewed_by` | Two-person rule for regulated domains |
| `created_at` / `last_verified_at` | Detect drift when corpus updates |
| `confidence` | Some questions are "slightly fuzzy" — track which |
| `is_known_failure` | Phase 1 will fail; record but don't fail the build |
| `corpus_version` | Re-validate when corpus changes |
| `golden_version` | Track which eval set version this entry belongs to |

### In this project
Current schema (see `eval/golden/v1.jsonl`):
```
qid, question, expected_answer_keywords, expected_book,
expected_chapter, expected_page_range, query_type, notes
```

**Design choices:**
- Started minimal — 7 required fields + `notes` for human review
- Used `keywords[]` not full reference answer — substring match is robust
  to phrasing changes, doesn't require an LLM judge for first-cut scoring
- `notes` field is a deliberate concession to "single-author project" —
  it captures provenance and verification reasoning that would, in a team,
  be in commit messages or review comments

**What I'd add at industry scale:** `created_by`, `reviewed_by`,
`last_verified_at`, `is_known_failure` (for `figure_or_diagram` queries that
Phase 1 is documented to fail), and `corpus_version` so a future OpenStax 3e
release doesn't silently invalidate page ranges.

---

## Decision 4 — Who owns it? (Roles in industry)

In a personal project this collapses to one person. In industry it's a
multi-stakeholder document with explicit role separation:

| Role | What they do | Why they're separate |
|---|---|---|
| **Domain SME** (e.g. doctor, lawyer, astronomer) | Writes questions, defines correct answers | Has the only valid mental model of "correct" |
| **Product Manager** | Defines query distribution that mirrors real users | Engineering tendency is to write technically-interesting questions, not user-realistic ones |
| **ML/Eval Engineer** | Operationalizes scoring, builds harness, runs evals | Owns the metric → has incentive to keep metrics consistent |
| **Reviewer (peer SME)** | Audits 10–20% of entries | Catches single-author blind spots |
| **Legal/Compliance** (regulated) | Validates question coverage of risk categories | The evaluator can't be the judge of risk coverage |

### The "one person can't" rule
Critical: **the person who writes the question and the person who verifies it
should not be the same**, especially in regulated domains. This is why FDA
submissions, legal AI, and medical AI all require multi-author review trails.

### The "product owns the bucket distribution" rule
Engineers write technically interesting questions. Real users ask boring,
repetitive, slightly malformed questions. The bucket *proportions* in the
golden set should reflect **real query distribution**, not engineer interest.
PM is the natural owner of "what fraction of queries are factual lookup
vs cross-document".

### In this project
**Single owner (me) plays all roles.** Acknowledged limitation. Mitigations:
- Pulling questions from OpenStax's published Review Questions (their domain
  experts effectively act as remote SMEs)
- Documenting reasoning in `notes` field as a stand-in for review trail
- Phase 2 A/B will catch some single-author bias by holding question set
  constant across two systems

**Interview talking point**: "If I were doing this on a team, I'd separate
question authoring from harness implementation, and I'd require that bucket
proportions be validated against actual query logs once we had them."

---

## Decision 5 — How do we know the golden is *actually* the truth?

This is the hardest meta-question. Three honest answers:

### Answer 1 — We don't, completely
A golden set is **a snapshot of what we currently believe is correct**. It is
not equivalent to ground truth. The textbook itself could be outdated. Domain
consensus could shift. Translations could vary.

The honest framing is: **golden set = "an authoritative reference, audited
and signed off by humans, whose limitations we document."** Not "the truth."

### Answer 2 — Calibration
The standard technique: have **humans answer ~30 questions blind** (without
the system) and compare their answers to the golden set's expected answers.
Disagreements between humans and the golden set are signal:
- Humans disagree → the question is ambiguous; rewrite or remove it
- Humans agree but golden disagrees → golden was wrong; fix it
- Humans agree with golden → golden is reliable on that question

This calibration is rarely done in practice because it doubles the upfront
cost. But for safety-critical systems (medical, legal) it's mandatory.

### Answer 3 — Triangulation
Multiple independent sources of truth:
- Question pulled from a textbook's review section (one source)
- Verified by `pdftotext` extraction of the source page (second source)
- Cross-checked against an external reference like Wikipedia (third source)

If three independent sources agree, the golden entry is high-confidence.
If two of three agree, medium. One source = low confidence; flag it.

### In this project
**Triangulation, not calibration.** I:
- Pull questions from OpenStax's published Review Questions where possible
- Verify each `expected_page_range` by `pdftotext`-extracting that page
  range and confirming the answer text is present
- For `cross_topic` questions, verify both chapters independently
- The `notes` field records this verification chain for audit

**What I deliberately did NOT do:** ask Gemini whether the golden answer is
correct. That's circular — Gemini's training data may be where the textbook
content originates, so its agreement is not independent evidence.

**Honest limitation in this project's eval (for the §9.4 honest-limitations
section of the A/B report):**
> "Golden set was authored by a single engineer with corpus access.
> Calibration against independent humans was not performed. Accuracy of
> `expected_page_range` was verified by direct PDF extraction; accuracy of
> `expected_answer_keywords` was not blindly verified against external sources."

---

## Decision 6 — How is the golden set audited?

Audit happens at three timescales:

### Pre-commit audit (per-question)
Before adding a question to the file:
1. Does it have all required schema fields?
2. Has `expected_page_range` been verified against the actual PDF?
3. Are `expected_answer_keywords` words that *must* appear (not synonyms)?
4. Is the `query_type` consistent with how the question is phrased?
5. Is the question answerable from the corpus alone, without external knowledge?

### Periodic audit (per-set, monthly/quarterly)
- Spot-check 10% of entries — re-verify page ranges and keywords
- Re-classify questions if `query_type` definitions evolved
- Mark questions stale if corpus version changed
- Remove questions that consistently score 100% — they no longer discriminate
- Review questions that consistently score 0% — are they unanswerable, or
  is the system genuinely failing?

### Drift audit (continuous, in production)
- When models upgrade, re-run eval — large score shifts mean the question's
  "correct" answer was model-specific (a problem)
- When corpus updates, re-verify all page ranges
- When user query distribution shifts, validate that bucket proportions
  still mirror real usage

### Industry tooling
Real eval governance often includes:
- **Versioned golden sets** committed to git, like code
- **Pull requests for new questions** with required reviewer
- **A "sandbox" golden set** for experimentation that doesn't affect the official one
- **Read-only "frozen" benchmark** that doesn't change between releases (regression detection)
- **Active learning loops** that surface low-disagreement examples for human review

### In this project
- **Pre-commit**: the `notes` field documents the verification chain for each entry
- **Periodic**: planned monthly review during active Phase 1 / Phase 2 work
- **Drift**: the schema includes implicit `corpus_version` (filename `astronomy-2e.pdf`); a 3e release would trigger full revalidation
- **Versioning**: file is `v1.jsonl`. Major rewrites become `v2.jsonl`; small additions stay in v1.

---

## Audit Log — real bugs caught while reviewing v1

Triangulation is not theoretical. Here's what audit caught in the first 4
questions of `v1.jsonl` — useful as both a reality check ("audit really finds
things") and as patterns to watch for in future entries.

### Bug 1 — astro-002: keyword that doesn't appear in the source
**What I wrote**: `"harmonic"` as an `expected_answer_keyword`.
**What the source actually says**: "**harmony of the spheres**" (a phrase, not "harmonic").
**Root cause**: I wrote keywords from memory of the concept, not from PDF
inspection. "Harmony" felt close enough to "harmonic" — but for substring
matching, those are different strings.
**Fix**: replaced with `"proportional"`, which is the actual word the source
uses to describe the P²∝a³ relationship.
**Pattern to watch for**: keywords derived from the *concept* rather than
the *literal text*. If you can't `pdftotext | grep` the keyword on the
expected pages, it's wrong.

### Bug 2 — astro-004: wrong page range
**What I wrote**: `expected_page_range: [88, 89]`.
**Where the answer actually was**: page **87** (the "Brahe was reluctant..."
sentence).
**Root cause**: Estimated page range without doing the `pdftotext` lookup.
Off-by-one because I was reading the printed page numbers in the OpenStax PDF
without confirming PDF-page index alignment.
**Fix (combined with Bug 3 below)**: question rewritten; new range verified.
**Pattern to watch for**: any `expected_page_range` not directly verified by
`pdftotext -f X -l Y | grep <keyword>`. If you didn't run that command,
the range is unverified.

### Bug 3 — astro-004: bucket label didn't match question structure
**What I wrote**: `query_type: "chapter_scoped"` for "Why was Brahe reluctant
to give Kepler all his data?"
**What was wrong**: The question had "In Chapter 3" in its phrasing, which
*looked* like chapter scoping. But the answer was a single sentence, in a
single paragraph, in a single section (§3.1). That's a `factual` question
wearing chapter_scoped clothing.
**Root cause**: I conflated *surface phrasing* ("In Chapter 3") with
*retrieval challenge* (does the system need to compose information from
multiple sections within a chapter?).
**Fix**: rewrote astro-004 entirely as a real chapter_scoped question that
spans §3.1 (Kepler's three laws), §3.3 (Newton's universal gravitation), and
§3.5 (Newton's reformulation of Kepler's third law). The new `notes` field
explicitly documents which sections must be retrieved.
**Pattern to watch for**: a `chapter_scoped` question whose answer fits in
one paragraph. If a single chunk could plausibly answer the question, the
bucket is wrong.

### Bug 4 — astro-005: same bucket-label mismatch, again
Same pattern as Bug 3, different question. astro-005 ("How was Neptune
discovered, and why is it called the first planet discovered through
mathematics?") was labeled `chapter_scoped` because the question said
"Within Chapter 3" — but the entire answer lives in §3.6 ("The Discovery
of Neptune") in two contiguous pages. Single section, single retrieval
challenge → `factual`.
**Fix**: relabeled to `factual`; removed the misleading "Within Chapter 3"
preface from the question text.
**Why this entry exists separately from Bug 3**: that the *same* bug
appeared in two consecutive entries shows it's not a one-off slip — it's
a systematic misunderstanding I had when first writing v1 ("if the
question mentions a chapter, the bucket is chapter_scoped"). Documenting
both occurrences makes the pattern recognizable in future audit waves.

### Bug 5 — astro-005: page-numbering convention undefined
Initially `expected_page_range: [107, 111]` looked correct via pdftotext —
but the OpenStax PDF has ~18 pages of front matter, so PDF page 107
corresponds to printed page 89. The schema didn't specify which numbering
to use. Without that convention, different questions could end up using
different conventions, silently breaking eval correlation between system
citations and golden expectations.
**Fix**: locked the convention to **PDF page indices** (matches pdftotext and
eventual ingestion pipeline; printed pages remain a UI concern). Documented
in `eval/golden/README.md` with the offset and verification command.
**Pattern to watch for**: any "page" field in any schema that doesn't
specify *which* page numbering. PDFs almost always have multiple
plausible answers (PDF index, printed page, section-relative page).
Lock the convention before writing the second question.

### Bug 6 — astro-006: schema couldn't represent cross-topic answers
**What I wrote**: `expected_book: "openstax-astronomy-2e-pt4"` and
`expected_page_range: [167, 170]` — a single book and a single page range
for a cross_topic question whose answer genuinely spans Ch.5 (in book part 1)
and Ch.26 (in book part 4).
**What was wrong**: the schema's single-string `expected_book` and
single-tuple `expected_page_range` couldn't express "the answer is in two
disjoint locations." Recording only one location either silently dropped
the other chapter from the eval ground truth, or forced a question-type
demotion. The 'cross_topic' bucket loses its meaning if the schema can't
represent it.
**Fix**: upgraded schema in `eval/golden/README.md` to plural list types:
`expected_books: str[]`, `expected_chapters: str[]`,
`expected_page_ranges: int[2][]`. All 8 v1 entries migrated; single-source
questions are 1-element lists, cross_topic gets multiple elements.
**Pattern to watch for**: any data shape that can't represent the most
ambitious bucket in your `query_type` enum is under-designed. Don't assume
"single source" is the universal default just because it covers most cases.

### Bug 7 — astro-006: page range only covered one of the two chapters
Even after the schema upgrade, the original `[167, 170]` only pointed at
Ch.5 and entirely omitted Ch.26 — meaning system retrieval from the
correct Ch.26 location would have been scored as a miss against an empty
ground truth.
**Fix**: replaced with `[[185, 189], [920, 924]]` — two PDF page ranges,
one per chapter, both verified by pdftotext extraction.
**Pattern to watch for**: when you upgrade a schema, *re-verify every
field you had to migrate*. Schema migration is when stale data is most
likely to hide.

### Bug 8 — astro-007 (and astro-006): printed page numbers leaked in
**What I wrote**: `expected_page_range: [900, 905]` for astro-007.
**Where the answer actually is**: PDF pages 920–921. Page 900 in the PDF
maps to a different chapter entirely.
**Root cause**: I wrote astro-007 *before* Bug 5 locked the page-numbering
convention. The original page range was the printed page number. The
convention got locked, but the existing question wasn't re-audited until
this pass.
**Fix**: re-verified Slipher's PDF location and updated to `[[920, 921]]`.
The same correction was needed in astro-006 (Ch.5 §5.6 was at PDF page
185, not printed page 167).
**Pattern to watch for**: conventions locked mid-project don't
automatically migrate existing entries. Whenever a convention changes,
schedule a "convention back-fill" audit pass — every entry written before
the lock is suspect until re-verified.

### Generalized lessons from the audit

1. **Bucket labels describe retrieval challenge, not question phrasing.**
   The bucket should be derived from "what must the retriever find?", not
   from how the question is worded. A factual question with chapter
   prefacing ("In Chapter 3...") is still factual. (Bugs 3 and 4 both
   stem from this confusion — when the same misconception produces two
   bugs, document the misconception, not just the fixes.)

2. **Every keyword and every page range is a claim that should be testable
   with `pdftotext | grep`.** If the verification command isn't trivially
   available, the entry is unverified.

3. **Lock conventions before they fragment.** Page numbering, chapter
   notation (`"3"` vs `"3.1"` vs `"Ch. 3 §3.1"`), book ID format —
   anything with multiple plausible representations needs a convention
   pinned down in the schema doc *before* the second question is written.
   Otherwise different entries quietly use different conventions and the
   eval harness's joins all break. (Bug 5 exemplifies this.)

4. **Audit catches different bugs than authoring.** When writing, you focus
   on intent ("what is this question testing?"); when auditing, you focus
   on evidence ("does the source actually support this?"). Both are
   necessary; neither replaces the other.

5. **9 real bugs across 8 audited questions (the full v1 set) is not a
   sign of carelessness — it's a sign that audit is working.** Bugs
   caught: a keyword that didn't exist in the source (Bug 1), a wrong
   page range (Bug 2), two bucket mislabels from a single misconception
   (Bugs 3, 4), a missing page-numbering convention (Bug 5), a schema
   too narrow for cross_topic (Bug 6), an incomplete migration leaving
   half a question unverified (Bug 7), and printed-page-number leakage
   in entries written before the convention lock (Bug 8). Two questions
   passed audit cleanly (astro-001, astro-008). Without audit, all of
   these would have silently skewed Phase 1 baseline numbers. The honest
   first-pass baseline is approximately **one bug per question** — not
   "writing carefully means audit will find nothing." Expect the rate to
   drop sharply on subsequent waves once these patterns are internalized,
   but plan for the first audit pass to be substantial work.

---

## The decisions, summarized as a checklist

When starting a new RAG project's eval, answer these in order:

```
[ ] Who has the authority to define "correct" for this domain?
    → That's your question author.

[ ] What's the smallest set that can give per-bucket signal?
    → That's your v1 size target. (Usually 30–50.)

[ ] What scoring metrics will I run?
    → Schema must provide every field those metrics consume. No more.

[ ] Who must sign off before this becomes "reference truth"?
    → Personal project: you, with documented reasoning.
       Team project: domain expert + reviewer + PM.
       Regulated: add legal/compliance.

[ ] How will I verify each entry is correct?
    → Triangulation if calibration is too expensive.
       Document the verification chain.

[ ] What triggers re-audit?
    → Corpus version change, model upgrade, query-distribution shift,
       or scheduled monthly review.
```

---

## Takeaway

**A golden set is not a test bank. It's a governance artifact.** Its quality
is bounded by who wrote it, how it's verified, and how it's kept honest as
the system evolves. The interview-version of this:

> *"I treat golden sets as living governance documents, not static test banks.
> Each question is owned by someone with authority over what 'correct' means
> in that domain, verified by a triangulation chain, and re-audited on a
> defined schedule. For this personal project I collapse all roles into one,
> but I document the verification chain in a `notes` field as a stand-in for
> the review trail a team would have."*

Companions:
- See `01-rag-eval-strategy.md` for what to *do* with a golden set once it exists.
- See `02-eval-before-deploy.md` for *when* in the project lifecycle to design it.
