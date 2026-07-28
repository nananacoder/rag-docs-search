"""LLM-judged quality metrics (RAGAS-style), via a direct Gemini judge.

Why not the RAGAS library: ragas pins its judge through
langchain-community's removed `chat_models.vertexai` shim, and the only
langchain generation that still ships it (0.2.x) uses pydantic-v1 compat
that chokes on langchain-google-vertexai's PEP-695 `TypeAliasType` under
Python 3.12 — a four-way (ragas / langchain / vertex / pydantic) deadlock.
Rather than freeze the whole stack to 2024 versions, these implement the
same three metric *definitions* with the project's already-working
google-genai client. Same energy as the no-ORM / no-LangChain-pg calls:
when the framework fights the platform, drop to the primitive.

Metrics (RAGAS definitions):
- faithfulness      — fraction of answer claims supported by the contexts
- answer_relevancy  — how directly the answer addresses the question (0-1)
- context_precision — fraction of retrieved contexts relevant to the question

Judge = Gemini (same family as the generator); the self-preference bias
cancels in the Phase 1 vs Phase 2 delta since the generator is identical
(docs/adr/008).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import mean
from typing import Any


@dataclass
class RagasScores:
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None


_FAITHFULNESS = (
    "You are grading whether an answer is grounded in its sources.\n"
    "Break the ANSWER into atomic factual claims. For each claim, decide if "
    "it is supported by the CONTEXTS (verbatim or by clear paraphrase).\n"
    "Ignore the closing 'Access for free at openstax.org' attribution.\n"
    "Return ONLY JSON: {{\"claims\": [{{\"claim\": str, \"supported\": bool}}]}}\n\n"
    "QUESTION: {question}\n\nCONTEXTS:\n{contexts}\n\nANSWER:\n{answer}"
)
_RELEVANCY = (
    "Rate from 0.0 to 1.0 how directly the ANSWER addresses the QUESTION "
    "(not whether it is correct — only relevance/on-topic-ness). A focused, "
    "complete response scores 1.0; an evasive or padded one scores lower.\n"
    "Return ONLY JSON: {{\"relevancy\": float}}\n\n"
    "QUESTION: {question}\n\nANSWER:\n{answer}"
)
_PRECISION = (
    "For each numbered CONTEXT, decide if it is relevant to answering the "
    "QUESTION.\nReturn ONLY JSON: {{\"relevant\": [bool, ...]}} with one entry "
    "per context, in order.\n\nQUESTION: {question}\n\nCONTEXTS:\n{contexts}"
)


def _client() -> Any:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
    from google import genai

    from app.core.config import get_settings

    s = get_settings()
    return (
        genai.Client(vertexai=True, project=s.gcp_project_id, location=s.gcp_location),
        s.gemini_model,
    )


def _judge_json(client: Any, model: str, prompt: str) -> dict[str, Any]:
    from google.genai import types

    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0, response_mime_type="application/json"
        ),
    )
    try:
        return json.loads(resp.text or "{}")  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return {}


def score_with_ragas(rows: list[dict]) -> list[RagasScores]:
    """Score each row: needs question, answer, contexts (list[str]).

    Rows missing an answer or contexts get an all-None RagasScores (skipped,
    not zeroed — a zero would understate the aggregate).
    """
    client, model = _client()
    out: list[RagasScores] = []
    for r in rows:
        question = r["question"]
        answer = (r.get("answer") or "").strip()
        contexts = [c for c in (r.get("contexts") or []) if c]
        if not answer or not contexts:
            out.append(RagasScores())
            continue

        ctx_block = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, 1))

        faith = _judge_json(client, model, _FAITHFULNESS.format(
            question=question, contexts=ctx_block, answer=answer))
        claims = faith.get("claims") or []
        faithfulness = (
            mean(1.0 if c.get("supported") else 0.0 for c in claims) if claims else None
        )

        rel = _judge_json(client, model, _RELEVANCY.format(
            question=question, answer=answer))
        relevancy = _clamp(rel.get("relevancy"))

        prec = _judge_json(client, model, _PRECISION.format(
            question=question, contexts=ctx_block))
        flags = prec.get("relevant") or []
        precision = (
            mean(1.0 if f else 0.0 for f in flags) if flags else None
        )

        out.append(RagasScores(
            faithfulness=faithfulness,
            answer_relevancy=relevancy,
            context_precision=precision,
        ))
    return out


def _clamp(v: Any) -> float | None:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None
