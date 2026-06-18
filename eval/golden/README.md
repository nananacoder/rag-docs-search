# Golden Eval Set — `v1.jsonl`

Hand-written question / expected-answer pairs against OpenStax *Astronomy 2e*.
Used by the eval harness to score retrieval and generation against a known-good
reference, producing the Phase 1 baseline that Phase 2 will be A/B-compared against.

## Schema

Each line is one JSON object:

| Field | Type | Notes |
|---|---|---|
| `qid` | str | Stable identifier, e.g. `astro-001` |
| `question` | str | The question, phrased naturally as a user would ask |
| `expected_answer_keywords` | str[] | Words/phrases that MUST appear in a correct answer (lowercased substring match at scoring time) |
| `expected_books` | str[] | List of book_ids (textbook parts) where the answer lives. Single-element for factual/chapter_scoped/figure_or_diagram; multiple for cross_topic. |
| `expected_chapters` | str[] | List of chapter numbers (parallel to `expected_books`). Single-element for most buckets; multiple for cross_topic. |
| `expected_page_ranges` | int[2][] | List of `[start, end]` inclusive **PDF page** ranges (see Page-numbering convention below). One range per source location — single-element for most queries, multiple for cross_topic spanning chapters. |
| `query_type` | str | One of `factual` / `chapter_scoped` / `cross_topic` / `figure_or_diagram` |
| `notes` | str | Provenance / verification notes (not used by harness; for human review) |

## Conventions (locked — do not vary across entries)

These are the format rules every entry MUST follow. They were locked after a
full v1 audit caught multiple bugs caused by inconsistent ad-hoc conventions
(see `learnings/04-golden-set-design-playbook.md` audit log). Any future
question that violates these is rejected by audit, regardless of how well it
otherwise reads.

### C1. `qid` format
**Rule**: `astro-NNN`, three-digit zero-padded sequence number, kebab-case
prefix, hyphen separator.
- ✅ `astro-001`, `astro-027`, `astro-142`
- ❌ `astro-1`, `astro_001`, `q1`, `001`
- Numbers do NOT reset across versions: if v1 ends at `astro-035`, v2
  starts at `astro-036`. Old qids are immutable references.

### C2. `expected_books` format
**Rule**: `openstax-astronomy-2e-pt{N}` where N ∈ {1, 2, 3, 4}, all lowercase,
kebab-case, abbreviated `pt`.
- ✅ `openstax-astronomy-2e-pt1`
- ❌ `openstax_astronomy_2e_pt1`, `OpenStax-Astronomy-Pt1`, `astronomy-2e/pt1`

Mapping from book_id → chapters covered:

| book_id | Chapters | Theme |
|---|---|---|
| `openstax-astronomy-2e-pt1` | 1–6 | Foundations & Methods |
| `openstax-astronomy-2e-pt2` | 7–14 | Solar System |
| `openstax-astronomy-2e-pt3` | 15–24 | Stars & Stellar Evolution |
| `openstax-astronomy-2e-pt4` | 25–30 | Galaxies, Cosmology & Life |

### C3. `expected_chapters` format
**Rule**: Plain integer strings only, no prefixes, chapter-level granularity
(NOT section-level).
- ✅ `"3"`, `"18"`, `"26"`
- ❌ `"Chapter 3"`, `"Ch.3"`, `"3.1"`, `"III"`, `3` (integer, not string)

Section-level info (`§3.1`, `§18.4`) goes in the `notes` field for human
reference, not in `expected_chapters`.

### C4. Page numbering — **PDF page indices, not printed pages**

`expected_page_ranges` uses PDF page indices, not the printed page numbers
visible to a human reader. These differ because the OpenStax PDF has ~18
pages of front matter (covers, preface, contents) before printed page 1.

| Type | Example | When to use |
|---|---|---|
| **PDF page** (what we store) | `107` | All schema fields; pdftotext indexing; eval harness; system citations internally |
| **Printed page** (book page numbers) | `89` | Human-facing UI display, "Access for free at openstax.org, p.89" |

Approximate offset for `astronomy-2e.pdf`: **PDF page ≈ printed page + 18**.
Verify by running `pdftotext -f N -l N astronomy-2e.pdf -` and checking the
visible page footer.

**Why PDF pages**: pdftotext (and any future Document AI ingestion) operates
on PDF page indices. Storing those directly makes verification trivial
(`pdftotext -f X -l Y astronomy-2e.pdf - | grep <keyword>`) and avoids an
error-prone offset translation step in the eval harness. Printed page numbers
can be derived for UI from the PDF page when needed.

### C5. Parallel-list alignment for cross_topic questions
**Rule**: When a question lists multiple sources (cross_topic), the indices of
`expected_books`, `expected_chapters`, and `expected_page_ranges` MUST align.
That is, source `i` is fully described by element `i` from each list.

Example (`astro-006`):
```jsonc
"expected_books":        ["openstax-astronomy-2e-pt1", "openstax-astronomy-2e-pt4"],
"expected_chapters":     ["5",                          "26"],
"expected_page_ranges":  [[185, 189],                   [920, 924]]
//                       └─── source 0 ───┘             └──── source 1 ────┘
```

### C6. `expected_answer_keywords` — case, punctuation, multi-word
**Rules**:
- **Case**: store keywords in their natural human-readable form (e.g.
  `"Tycho Brahe"`, `"Hertzsprung"`). The eval harness normalizes both the
  answer and keywords to lowercase before substring match. Storing them
  human-readably makes review and PR diffs intelligible.
- **Multi-word keywords are allowed and encouraged** for proper nouns and
  technical phrases (`"orbital period"`, `"main sequence"`, `"inverse
  square"`). Substring matching handles them transparently.
- **Numbers carry their unit** when meaningful (`"1800 kilometers"`, not just
  `"1800"`). The unit prevents accidental matches on unrelated occurrences.
- **No leading/trailing whitespace.** No internal double spaces.
- **3–6 keywords per question** is the target range (see
  `learnings/05-keyword-set-design.md`).

### C7. `query_type` — exactly one of four values
**Allowed values** (case-sensitive, snake_case):
- `factual` — answer in a single passage / single section
- `chapter_scoped` — answer requires synthesizing across multiple sections within ONE chapter
- `cross_topic` — answer requires retrieval from TWO or more chapters
- `figure_or_diagram` — question explicitly references a named figure/diagram

The bucket is determined by **retrieval challenge**, not question phrasing.
A question that says "In Chapter 3, what is X?" but whose answer is in one
paragraph is `factual`, not `chapter_scoped`. (See `learnings/04` Bugs 3
and 4 for why this rule exists.)

### C8. `notes` — provenance and verification audit trail
**Rule**: every entry's `notes` field MUST contain at minimum:
1. `Source:` — which chapter / section
2. A one-sentence summary of why this is the correct answer
3. `PDF pages verified by pdftotext.` — explicit attestation that page
   range was checked

Recommended structure:
```
Source: Ch.X §X.Y; <one-sentence factual summary>. PDF pages verified by pdftotext.
```

For cross_topic, `notes` MUST explicitly call out that retrieval is required
from MULTIPLE chapters, and identify each chapter and its role.

For questions whose bucket was changed during audit, `notes` MUST record the
change ("Bucket downgraded from chapter_scoped to factual on audit: ...").

### Open design question (not locked yet)

**Single PDF file, multiple logical `book_id`s.** The corpus is one physical
PDF (`astronomy-2e.pdf`) but logically split into 4 `book_id`s by chapter
range. The mapping is currently maintained only in C2's table. When ingestion
runs, will it actually produce 4 separate Cloud Storage objects (one per
part), or one object with metadata? This affects:
- How `expected_books` joins to retrieved chunks at eval time
- Whether the user-facing UI's "scope to part X" filter makes physical or
  logical sense
- Migration to a future multi-PDF corpus (e.g. adding a second textbook)

This question is left **open** until Phase 1 ingestion is designed in detail.
The schema convention here (one logical book_id per chapter range) is
sufficient for v1 eval purposes, but the ingestion contract will need to
reconcile it.

## v1 set (8 questions — starter)

| qid | bucket | source chapters |
|---|---|---|
| astro-001 | factual | 3 (Brahe + Kepler) |
| astro-002 | factual | 3 (Kepler's third law) |
| astro-003 | factual | 3 (Newton universal gravity) |
| astro-004 | chapter_scoped | 3 (Kepler's laws → Newton's gravity → Newton's reformulated 3rd law; spans §3.1, §3.3, §3.5) |
| astro-005 | factual | 3 (Neptune discovery, §3.6) |
| astro-006 | cross_topic | 5 + 26 (redshift → Hubble) |
| astro-007 | factual | 26 (Slipher's spectra) |
| astro-008 | figure_or_diagram | 18 (H-R diagram) |

This is a starter set heavily weighted to Chapter 3 because that's where
verification was most thorough. Subsequent versions (`v2`, `v3`) should:

- Spread across more of the 30 chapters
- Add 2–3 more `cross_topic` questions (currently only one)
- Add 2–3 more `figure_or_diagram` questions (currently only one)
- Target 30–50 total questions before considering the eval set "complete"

## How to extend

1. Pick a chapter you've read sample pages of
2. Look at the chapter's end-of-chapter Review Questions for `factual` material
3. For `cross_topic`, hand-write a question that requires content from ≥ 2 chapters
4. For `figure_or_diagram`, look at named figures in the chapter (HR diagram, electromagnetic spectrum, galaxy types)
5. Verify `expected_page_range` by `pdftotext`-ing those pages and confirming the answer is there
6. Append to `v1.jsonl` (or branch `v2.jsonl` for major revisions)

## Why hand-written

LLM-generated golden sets are convenient but circular: the evaluator and the
test creator share the same biases, and synthetic questions tend to reflect
"easy-to-extract" patterns rather than "what users actually ask." A small
hand-written set of 30–50 questions is more credible for portfolio-level work,
and writing it forces familiarity with the corpus that pays off in eval design.

See `learnings/01-rag-eval-strategy.md` for the broader rationale.
