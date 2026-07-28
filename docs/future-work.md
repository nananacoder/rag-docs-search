# Future Work — "What would you do next?"

Interview answer to *"with more time / budget, what would you improve?"*
Ordered by **leverage** (value ÷ effort), not by interest. The discipline is
the point: knowing what to do first — and what NOT to do — matters more than
the list.

The honest one-liner: *"The architecture is proven and measured. What's left
is (1) finishing the one metric that got blocked, (2) making the eval
statistically harder to argue with, and (3) closing the latency gap. Only
after those would I chase newer retrieval tech."*

---

## Tier 1 — Finish the thesis (cheap, high value)

### 1.1 Complete the RAGAS A/B (blocked, ~1 hour, ~¥15)
The direct-Gemini judge is built and validated (faithfulness caught an
ungrounded claim at 0.667), but the full 8-question × 2-arm run was blocked
by a port-3307 firewall on teardown day (learnings/11 §9). **Do**: rebuild
Cloud SQL from caches, run `run_eval.py --ragas` for Phase 2 and Phase 1,
fill the 4 `‹RAGAS›` cells + 5 case studies in the A/B report.
**Why first**: it's the one planned deliverable left unfinished, and
faithfulness/relevancy are the metrics keyword-overlap can't capture — they
turn "86% keyword" into "and the answers are actually grounded."

### 1.2 Grow the golden set 8 → 30–50 questions (~half a day)
Every number today is "on 8 hand-verified questions" — directional, not
tight. **Do**: expand with the same audit rigor (the 8-question set caught 9
bugs; scale that), add per-question **reference answers** so `context_recall`
and answer-correctness become computable. **Why**: turns "suggestive" into
"defensible," and unlocks the RAGAS metric currently deferred for lack of
references.

### 1.3 Figure-citation bbox fix (~2 hours)
Figure chunks carry whole-image bboxes, so the citation range-check
under-scores them (figure bucket citation ~20% despite 100% keyword). **Do**:
fall back to page-level citation for `modality='figure'`, or store the
caption's text span. **Why**: cheap, and closes the most visible remaining
gap in the citation story.

## Tier 2 — Make it faster and more honest (medium effort)

### 2.1 Cut the ~19.6s p50 latency
The ef_search sweep proved retrieval is ~0.2s — the budget is the two Gemini
calls (rerank + generation). **Do, in order**: (a) stream the generator
first token sooner (perceived latency); (b) shrink rerank passages / batch
smarter; (c) A/B a dedicated reranker (Voyage rerank-2.5-lite, ~<100ms) as a
controlled Phase 2.5 experiment — hold everything else, swap only the
reranker. **Why**: 19.6s is the honest cost of the quality gain; it's also
the thing a real user would complain about first.

### 2.2 Reranker score-calibration review (~1 hour)
The reranker already logs per-query score distributions (learnings/10 Add 2).
**Do**: after ~100 queries, check for tight clustering (e.g. everything
7–9) — if it isn't discriminating, switch to rank-position selection. **Why**:
operational hygiene; proves the rerank step earns its latency.

### 2.3 Eval regression gate in CI (~2 hours)
**Do**: GitHub Actions runs lint + mypy + mock-backend tests on every PR;
a manual workflow runs the paid eval and fails if faithfulness drops >2% vs
baseline. **Why**: makes "don't regress retrieval quality" mechanical.
Deliberately deferred so far (single-dev), but it's the natural next
maturity step and a clean thing to show.

## Tier 3 — Deploy & scale (higher cost, situational)

### 3.1 Cloud Run deployment
Designed, never deployed (retrieval scores are identical local vs deployed;
only latency profile changes). **Do it if** a live demo URL is worth the
~¥15/mo + cold-start latency. Note: solves the port-3307 problem too (the
service account connects over the platform's private path).

### 3.2 Document AI upgrade
$11.5 for precise per-block bbox + official layoutType. Deferred after
measuring its unique value is bbox precision — a UI concern, not a retrieval
metric (ADR-006). **Do it if** pixel-perfect highlighting becomes a
requirement; otherwise the pymupdf + Gemini Vision path stays.

### 3.3 Multi-book corpus
The schema and hybrid SQL already support N books (the 4-part split proves
it). **Do**: add a second textbook to test cross-book scoping and whether
retrieval quality holds at larger scale. **Why**: turns a single-corpus demo
into a "does it generalize" story.

## Tier 4 — Research bets (only after Tiers 1–2 land)

Each is a **controlled Phase-3 experiment**: same eval, swap one variable.

- **Contextual Retrieval measurement**: it's implemented; run the ablation
  (with/without prefixes) to *quantify* its recall lift on this corpus, not
  just cite Anthropic's numbers.
- **ColPali** (page-image late-interaction): dodges OCR/structural-noise
  entirely, but needs a different (multi-vector) storage design — rewrites
  Phase 2. Deferred to Phase 3 (learnings/10 Deferral 1).
- **GraphRAG**: value shows on many-document corpora; marginal for one
  textbook until the corpus scales (learnings/10 Deferral 2).
- **Gemini Embedding 2**: currently on `gemini-embedding-001` (Embedding 2
  is allowlist-gated). Swap and re-measure when it hits GA — as a separately
  controlled variable, not mixed into the managed-vs-self-built thesis.

---

## What I would deliberately NOT do

Naming these is half the point in an interview:
- **Chase every new RAG paper** — the architecture is measured; unmeasured
  novelty is a step back.
- **Add a framework (LangChain/LlamaIndex)** — three times this project
  dropped a framework (ORM, LangChain-pg, RAGAS-lib) because it fought the
  platform harder than the problem. Consistency of judgment > tooling.
- **Over-build the eval harness** — a 30-question golden set + RAGAS is the
  right rigor for this scope; a full four-layer eval pyramid would be
  eval-for-eval's-sake here.

> **Interview close**: *"The ranking is the answer. I'd finish the blocked
> RAGAS run and harden the eval before touching anything newer — because the
> project's value is that its numbers are trustworthy, and you protect that
> before you chase the next technique."*
