"""RAGAS scoring layer for the eval harness (learnings/10 Adoption 4).

Offline, LLM-judged quality metrics that keyword-overlap can't capture:
whether the answer is grounded (faithfulness), on-topic (answer relevancy),
and whether retrieval surfaced useful context (context precision).

Judge = Gemini via Vertex — the SAME family as the generator. That carries
a known self-preference bias, but the Phase 1 vs Phase 2 A/B holds the
generator identical, so the bias is applied equally to both arms and
cancels in the delta (docs/adr/008). Swap to a heterogeneous judge only
when comparing different generators.

Metrics computed (3 of RAGAS's set):
- faithfulness            — answer claims supported by retrieved contexts
- answer_relevancy        — answer addresses the question (needs embeddings)
- context_precision       — reference-free: are retrieved contexts useful
context_recall is intentionally omitted: it needs per-question reference
answers the golden set doesn't carry yet (a golden-v2 task).

Heavy deps, installed only for the paid run — NOT in the api's core deps:
    pip install "ragas>=0.2" langchain-google-vertexai
Everything here imports lazily so `run_eval.py` works without ragas unless
--ragas is passed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RagasScores:
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None


def score_with_ragas(
    rows: list[dict],
    judge_model: str = "gemini-2.5-flash",
    embed_model: str = "text-embedding-005",
) -> list[RagasScores]:
    """Score each row. A row needs: question, answer, contexts (list[str]).

    Returns one RagasScores per row, aligned by index. Any row missing an
    answer or contexts yields an all-None RagasScores (skipped, not zeroed
    — a zero would understate the aggregate).
    """
    from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        Faithfulness,
        LLMContextPrecisionWithoutReference,
        ResponseRelevancy,
    )

    llm = LangchainLLMWrapper(ChatVertexAI(model=judge_model, temperature=0.0))
    embeddings = LangchainEmbeddingsWrapper(VertexAIEmbeddings(model_name=embed_model))
    metrics = [
        Faithfulness(llm=llm),
        ResponseRelevancy(llm=llm, embeddings=embeddings),
        LLMContextPrecisionWithoutReference(llm=llm),
    ]

    # Only score rows that actually have an answer + contexts; keep a map
    # back to original indices so the caller can align scores to entries.
    scorable: list[int] = []
    samples: list[SingleTurnSample] = []
    for i, r in enumerate(rows):
        answer = (r.get("answer") or "").strip()
        contexts = [c for c in (r.get("contexts") or []) if c]
        if not answer or not contexts:
            continue
        scorable.append(i)
        samples.append(
            SingleTurnSample(
                user_input=r["question"],
                response=answer,
                retrieved_contexts=contexts,
            )
        )

    out = [RagasScores() for _ in rows]
    if not samples:
        return out

    result = evaluate(EvaluationDataset(samples=samples), metrics=metrics)
    df = result.to_pandas()
    for local_i, orig_i in enumerate(scorable):
        row = df.iloc[local_i]
        out[orig_i] = RagasScores(
            faithfulness=_get(row, "faithfulness"),
            answer_relevancy=_get(row, "answer_relevancy"),
            context_precision=_get(row, "llm_context_precision_without_reference"),
        )
    return out


def _get(row: object, col: str) -> float | None:
    import math

    try:
        val = float(row[col])  # type: ignore[index]
    except (KeyError, TypeError, ValueError):
        return None
    return None if math.isnan(val) else val
