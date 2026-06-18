# 03 — Corpus Pivot: From History Books to OpenStax Astronomy

**Date**: 2026-05-21
**Tags**: corpus-design, license, eval, decision-making

## Question I started with
"The project doc names a Project Gutenberg history corpus (Gibbon, Thucydides,
Herodotus, Plutarch). I'm about to start writing the golden eval set against it.
Step one is downloading the PDFs. Should be 5 minutes — what could go wrong?"

## Short answer
Corpus selection is not the trivial first step it appears to be. It has hard
constraints — license cleanliness, real text layer, modern electronic typesetting,
multimodal content, modern relevance — that **almost no single source satisfies
simultaneously**. Discovering this *before* infrastructure deployment is the
entire point of front-loading corpus work.

---

## The constraints, in the order they collided

### 1. Project Gutenberg has no PDFs
The original doc assumed "Gutenberg history books as PDFs." Verified by checking
several editions: Gutenberg offers HTML, EPUB, plain text, Kindle — **never PDF**.
The downstream stack (Vertex AI Search layout parser, Document AI Layout Parser,
the Angular PDF pane with bbox highlighting) all assumes PDF input.

**Three escape routes**:
- HTML → PDF conversion (loses real page numbers)
- archive.org scanned PDFs (need OCR; Phase 1 explicitly defers OCR)
- Switch to HTML/text input (would invalidate Phase 2's bbox citation story)

### 2. The 19th-century-translation trap
Public-domain English translations of these works (Gibbon's editor Milman †1868;
Thucydides translator Crawley †1893; Herodotus translator Macaulay †1915) are
all old enough to be free of copyright. **But that same age means** modern
electronic typesetting doesn't exist for them. Anything you can buy or download
is either:
- A scan of a 19th-century printing (no clean text layer)
- A modern *new* translation (in copyright)

So "want clean PDF + want public domain + want pre-1900 work" is a
**three-corner constraint where two corners cancel the third**.

### 3. The "z-library Penguin" temptation
Modern translations (Penguin Classics, Loeb, Landmark) have everything — clean
PDFs, beautiful maps, modern typography. They also have copyright. Using them
in a corpus you'll surface in interviews is a license-cleanliness failure
that's *visible to anyone who asks where the corpus came from*. It's not a
likely-to-be-prosecuted issue for a personal project; it **is** an interview
signal that suggests you don't take license boundaries seriously in
production-adjacent work.

### 4. NASA reports — close, but the search-keyword trap
After ruling out classical works, NASA technical reports looked perfect:
US-government public domain, modern PDFs, mission technical detail. But the
first batch of "Mars mission overview" downloads turned out to be:
- A NEPA legal Record of Decision (12 pages, no science)
- A Small Business Programs achievement brochure (20 pages, no science)
- A 2-page Ingenuity fact sheet
- One actual technical paper on the Adaptive Caching Assembly

**Generic search terms** ("mission overview") match more PR / administrative /
boilerplate documents than they do real technical reports. To get genuine
technical content from NTRS you have to search by instrument name, EDL phase,
or specific subsystem — terms that imply you already know what you're looking for.

### 5. The "old enough = scanned" rule reasserts itself
Considered NASA's classic SP-series astronomy monographs (SP-345 *Evolution of
the Solar System*, SP-419 *The Galaxy and the Solar System*, etc.). These are
scientifically deep and definitely public domain. But they were published
1970s–80s as printed books and only digitized later as **scans**. The same
pattern that ruled out Gibbon: depth and public-domain-ness correlate with age,
which correlates with scanned-only availability.

---

## The constraints, distilled

The corpus must satisfy **all** of these:

| Constraint | Why |
|---|---|
| Real text layer in the PDF | Phase 1 doesn't have OCR; Phase 2's BM25 is destroyed by OCR errors |
| License clean | License-shadiness shows up the moment someone asks "where's the corpus from?" |
| Multi-chapter structure | Drives the `chapter_scoped` and `cross_topic` query buckets |
| Multimodal content | Drives the `figure_or_diagram` bucket and Phase 2's vision pipeline |
| Modern electronic typesetting | Avoids OCR; gives Document AI clean blocks to parse |

The pattern is: each candidate solves 3–4 of these and fails 1. The hunt is
for one that solves all 5.

---

## Where it landed: OpenStax *Astronomy 2e*

**OpenStax** is a free open-textbook initiative led by Rice University, with
real domain experts as authors. *Astronomy 2e* (Fraknoi, Morrison, Wolff,
2026) checks every box:

| Constraint | Status |
|---|---|
| Real text layer | ✅ Prince XML-generated PDF, clean and recent |
| License | ✅ CC BY-NC-SA 4.0 — non-commercial use is exactly this project |
| Multi-chapter | ✅ 30 chapters, hierarchical sections (3.1, 3.2, ...) |
| Multimodal | ✅ Many figures: H-R diagram, EM spectrum, galaxy taxonomy, photographs |
| Modern typesetting | ✅ 2026 edition, professional layout |

The license is **CC BY-NC-SA 4.0**, not the more permissive CC BY 4.0 I
initially expected. NC (non-commercial) is fine for a portfolio project; SA
(share-alike) only matters if the project itself is published as a derivative
work, which it isn't. The required attribution string ("Access for free at
openstax.org") is surfaced in every API response — turning license compliance
into a small but visible engineering detail.

### Project changes triggered by the pivot

| Layer | Change |
|---|---|
| README, phase1, phase2, technical-design | Corpus, examples, prompt templates rewritten |
| Mock retriever fixture | Real OpenStax content (Kepler in Ch. 3, Carrington in Ch. 15, Slipher in Ch. 26) |
| Eval bucket design | `cross_book` → `cross_topic` (within one textbook); `figure_or_map` → `figure_or_diagram` |
| Chapter detection regex | `^Chapter \d+` and `^\d+\.\d+` (OpenStax format) instead of `^CHAPTER [IVXLC]+` |
| Hybrid retrieval H1 example | Scientific proper nouns (Chandrasekhar, Cepheid, Schwarzschild) instead of historical (Commodus, Thermopylae) |
| Document AI prompt for figure captions | "axis labels, scientific quantities, celestial objects" instead of "place names, routes, battle plans" |

The two-phase architecture, the eval framework, the GCP deployment, the
hybrid-retrieval-vs-managed comparison — all unchanged. **Only the corpus
domain moved.** That separation between "things tied to the corpus" and
"things tied to the system" is itself a useful interview point: a well-designed
RAG system should let you swap corpus without rewriting the architecture.

---

## What's interview-worthy here

### The decision principle
*"Corpus selection is not a 5-minute step before the real work. It is a
co-equal design decision with the system architecture and the evaluation
framework, because it imposes constraints that propagate into every layer
of the system."*

### The constraint analysis
The five-corner constraint (text layer / license / structure / multimodal /
modern typesetting) is a generalizable framework. For any RAG corpus
selection:
1. List the hard constraints from your **system design**
2. List the hard constraints from your **product promise**
3. List the hard constraints from **legal / governance**
4. Find the corpus that satisfies all three sets, not just the appealing two

### The license-cleanliness signal
Choosing OpenStax over a scanned modern translation is a **costly signal**:
it costs nothing to use a slightly nicer corpus, but doing so demonstrates
license awareness without anyone asking. In an interview, "I deliberately
avoided X because of license concerns" is a higher-trust signal than
"I didn't think about license."

### The architecture-corpus separation
The fact that pivoting from history books to an astronomy textbook required
zero changes to the two-phase architecture, the GCP infrastructure design,
or the eval framework — and only domain-level changes to prompts, regex
patterns, and bucket names — is a sign the original design factored those
concerns correctly. Corpus-coupled and corpus-independent concerns were
already separated.

---

## Takeaway

**The "5-minute corpus selection" was actually 3 hours of failed candidates,
4 license discussions, 2 false positives on NTRS, and one real lesson:
constraint analysis before commitment is the cheapest engineering tool
in the box.**

Front-loading corpus work — *before* deploying infrastructure, before
writing the golden eval set, before bucketing query types — caught
problems that would have been brutally expensive to discover after Phase 1
was already running on GCP. This is also exactly why the eval-design-first
principle from `02-eval-before-deploy.md` extends to corpus design too:
**both the questions you'll evaluate against and the documents you'll
retrieve from must be locked before you spend cloud dollars on either.**
