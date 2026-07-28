# ADR-008: RAGAS judge = Gemini (same family as the generator)

**Status**: Accepted (M6). Judge model: Gemini 2.5 Flash via Vertex.

## Context
RAGAS scores faithfulness / answer relevancy / context precision with an
LLM judge. Using the generator's own model family (Gemini) as judge risks
**self-preference bias** — LLM judges tend to favor outputs in their own
style (a documented LLM-as-judge failure mode).

## Decision
Use Gemini as the judge anyway.

## Why it's valid here
The project's headline result is a **Phase 1 vs Phase 2 A/B with the
generator held identical** (same Gemini 2.5 Flash, same prompt — the whole
point of the controlled experiment). Any self-preference bias the Gemini
judge carries is therefore applied **equally to both arms** and cancels in
the delta. This is the same control logic as freezing the embedding model
and the prompt: a confound that is constant across arms doesn't move the
measured difference.

## When this would be wrong
The moment the comparison involves **different generators** (e.g. a future
"Gemini vs Claude generator" test), the bias stops cancelling and a
heterogeneous judge (e.g. Claude judging, or an ensemble) becomes
mandatory. The judge choice is a function of what's being compared, not a
fixed default.

## Also noted
Absolute RAGAS values (not just the delta) are still reported for context,
but interpreted with this bias in mind — the trustworthy signal is the
Phase 1→Phase 2 movement, not the absolute number.
