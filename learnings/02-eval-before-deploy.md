# 02 — Why Eval Strategy Comes Before Deployment

**Date**: 2026-05-20
**Tags**: eval, project-planning, cost, methodology

## Question I started with
"Why does the eval strategy have to be designed *before* deployment? Can't I just
deploy first, see how it works, and figure out evaluation later?"

## Short answer
Deployment costs money and is hard to undo. Eval design is the requirements doc,
the definition of done, and the value proof for that deployment. All three must
exist *before* the deploy, or the deploy produces no useful signal.

---

## Five reasons, from most pragmatic to most fundamental

### 1. Eval design retroactively decides what to deploy

The bucket choices in `phase1-managed.md §3.9` aren't decoration — they're
specifications:

- `figure_or_map` bucket exists → **the corpus must include illustrated/mapped books**
- `chapter_scoped` bucket exists → **the corpus must have clear chapter structure**
- `cross_book` bucket exists → **need ≥3 books with overlapping subject matter**

If you deploy first and pick 5 random Gutenberg PDFs, you may discover later
that two buckets have nothing to evaluate against. Then you either weaken the
eval (compromise) or redo the corpus (re-deploy = re-spend money on indexing,
storage, and Vertex AI Search bulk-import quotas).

**Eval design is the requirements document for deployment**, not the
post-deployment checklist.

### 2. A deployment without a baseline is essentially worthless

Phase 1's entire purpose is to establish a measurable baseline that Phase 2's
A/B comparison rests on.

Without baseline numbers:
> "I built a self-hosted hybrid retrieval system!" — Better than what?

With baseline numbers:
> "Phase 1 scored 0.55 on cross_book; Phase 2 improved it to 0.75 (+0.20),
> driven by these specific design choices."

If you deploy Phase 1, take it down to save cost (scale-to-zero,
`activation-policy=NEVER` on Cloud SQL), and *then* design eval — **the baseline
is unrecoverable** unless you bring Phase 1 back up and pay again. Phase 1's
managed services aren't free to leave running, so the baseline window is
narrow and one-shot.

### 3. Eval defines "done" for the deployment

Without an eval standard, "deployment done" is hand-wavy:
- I tested 5 questions manually, looked fine — done?
- API returns 200 — done?
- Vertex AI Search reports indexing complete — done?

With an eval standard:
- 30 golden questions executed, 5 metrics recorded
- ≥3 of 4 buckets above their thresholds
- Run card committed to `eval/runs/phase1-v1.md`

The first version traps you in an infinite "looks ok, but maybe tweak more"
loop. The second has a hard finish line. **Engineering work without a
defined-done is engineering work that doesn't end.**

### 4. Designing eval forces you to discover architecture issues — while they're cheap to fix

Writing golden questions is a structured exercise in *imagining what users will
actually ask*. That exercise reveals system gaps:

| Question I'd write | Discovery it forces |
|---|---|
| "What was Hannibal's invasion route?" | Phase 1 has no image understanding → `figure_or_map` is a known-failing bucket; document it as Phase 2's win |
| "How do Thucydides and Gibbon differ on democracy?" | Cross-book retrieval is weak in Phase 1; Phase 2's hybrid + RRF is the planned fix |
| "I want citation precision down to the paragraph" | Phase 1 has page-level only; bbox highlighting is a Phase 2 capability |

**These discoveries are only valuable before deployment.** They directly
influence:
- What lands in Phase 1 vs Phase 2 (scope)
- Which query types are known-failing (reported, not blocking)
- What the prompt template needs to handle ("if you don't know, say so")

Discovering them post-deployment means rework: redesign, re-deploy, re-eval.

### 5. The eval harness itself has bugs — debug them with mock data

The eval pipeline is code, and code has bugs:
- RAGAS API calls fail (rate limit, credential, JSON parse)
- Citation accuracy formula has off-by-one errors
- Bucket classification rules are ambiguous

Running the harness against the **mock retriever and mock generator** lets you
validate that:
- Golden set file format parses
- Eval script can hit the API end-to-end
- Report generation and commit flow work
- Each metric's calculation is correct (even if scored against fake data)

If you debug eval code post-deployment, **every harness run burns real
Vertex AI Search query costs** for what is effectively a syntax check. The
mock environment is a free test bed for the harness — and it only exists
*before* you cut over to real retrieval.

---

## What eval work can be done before deploy (almost all of it)

| Task | Needs GCP? | Pre-deploy? |
|---|---|---|
| Select corpus books | No | ✅ |
| Design query_type buckets | No | ✅ |
| Write 30–50 golden questions (with `expected_page_range` validated against the actual PDFs) | No (manual PDF review) | ✅ |
| Implement eval harness (RAGAS + citation accuracy) | No (against mock backend) | ✅ |
| Smoke-test eval pipeline end-to-end | No (mock mode) | ✅ |
| **Run harness against real retrieval, record baseline** | Yes | ❌ — only this one needs deployment |

Five out of six steps cost zero GCP dollars. Deployment unlocks step 6 only.

---

## The deeper principle

This isn't unique to RAG eval. It's a general engineering rule:

> **Front-load the cheap, decision-locking work. Back-load the expensive,
> reversible-only-with-cost work.**

Eval design has near-zero cost (paper + thought) but locks down a lot
(corpus choice, scope split, definition of done, success criteria). Deployment
costs real money, time, and quota, and undoing it is messy. Doing them in the
wrong order — deploy first, design eval later — is the same mistake as writing
production code before agreeing on requirements.

In `phase1-managed.md`, this principle is encoded structurally: the eval
harness section (§3.9) appears in the same Implementation Steps list as the
infra runbook (§3.1), not as a follow-up. They're co-equal.

---

## Takeaway

**Eval strategy is the requirements document, the completion definition, and
the value proof for a deployment. Without it, you can't decide what to deploy,
recognize when you're done, or demonstrate that the deployment was worth the
spend.**

The interview-version of this:
*"I designed eval before deploying because the eval is what makes the
deployment legible. Without a defined success metric and a golden set, Phase 1's
output is unmeasurable, and the entire two-phase A/B narrative collapses.
Designing eval first also revealed scope decisions — which queries belong to
Phase 1 vs Phase 2 — that would have caused rework if discovered later."*
