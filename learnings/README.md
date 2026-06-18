# Learnings — Project Journal

Design decisions, evaluation strategy, RAG/LLM/eval engineering thinking.
Records what I figured out, why I made the choice, and what's worth telling
in an interview.

> **Scope:** RAG architecture, retrieval/generation tradeoffs, evaluation
> design, LLM-side decisions, and engineering principles that shaped the
> system. Routine FE/BE coding bugs do **not** belong here.

## Index

### Evaluation
- [01 — RAG eval: why "classic + standard" still means adapting to your corpus](./01-rag-eval-strategy.md)
- [02 — Why eval strategy comes before deployment](./02-eval-before-deploy.md)
- [04 — Golden set design playbook: how to build the "reference truth"](./04-golden-set-design-playbook.md)
- [05 — Designing `expected_answer_keywords`: synonyms, OR-relations, and the real purpose](./05-keyword-set-design.md)
- [06 — Golden set at industrial scale: beyond the hand-written 30](./06-golden-set-at-scale.md)

### Corpus / Data
- [03 — Corpus pivot saga: from history books to OpenStax Astronomy](./03-corpus-pivot-saga.md)

### Infrastructure / GCP
- [07 — Vertex AI Search setup: REST API traps and SDK wins](./07-vertex-ai-search-setup.md)

### Phase 1 Results
- [08 — Phase 1 baseline: when "bad" numbers are the point](./08-phase1-baseline-interpretation.md)

### Retrieval / Architecture
- [09 — Vector DB landscape: why pgvector for this project (and what I got wrong)](./09-vector-db-landscape.md)
- _(coming — chunking strategy, hybrid retrieval rationale, etc.)_

### LLM / Generation
- _(coming — prompt design, citation grounding, router/escalation, model selection)_

### Engineering
- _(coming — ingestion pipeline, observability, cost controls)_

---

## Entry template

Each entry roughly follows:

1. **Question I started with** — the prompt, often a real moment of confusion
2. **Short answer** — 1–3 sentences someone could repeat after hearing it
3. **Body** — the reasoning, usually with comparison tables, signals,
   counterexamples, domain-specific notes
4. **Implications for this project** — what it means concretely here
5. **Takeaway** — what's interview-worthy / generalizable

Length isn't fixed. A small decision can be 1 page; a big strategic one can
be longer. Not every section is mandatory.
