"""Gemini Flash LLM reranker (§5.2): score top-20 fused candidates 0-10,
keep top-k. Falls back to RRF order on any parse/API failure — retrieval
must never hard-fail because reranking hiccupped.

Logs the score distribution per query (learnings/10 Add 2): if scores
cluster tightly over ~100 queries, the reranker isn't discriminating.
"""

import json

from google import genai
from google.genai import types

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.rows import SearchHit

log = get_logger(__name__)

_PROMPT = (
    "Given this query: {query!r}\n\n"
    "Score each numbered passage below from 0 to 10 for how useful it is "
    "for answering the query. Output ONLY a JSON array of integers, one "
    "score per passage, in order.\n\n{passages}"
)


class GeminiReranker:
    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self.settings = settings
        self._client = client or genai.Client(
            vertexai=True, project=settings.gcp_project_id, location=settings.gcp_location
        )

    async def rerank(
        self, query: str, hits: list[SearchHit], keep: int
    ) -> list[SearchHit]:
        if len(hits) <= keep:
            return hits
        passages = "\n\n".join(
            f"[{i}] {h.content[:1200]}" for i, h in enumerate(hits, start=1)
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self.settings.gemini_model,
                contents=_PROMPT.format(query=query, passages=passages),
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            scores = [float(s) for s in json.loads(response.text or "[]")]
            if len(scores) != len(hits):
                raise ValueError(f"got {len(scores)} scores for {len(hits)} passages")
        except Exception as exc:  # fall back to RRF order, never fail retrieval
            log.warning("rerank_fallback_rrf_order", error=str(exc))
            return hits[:keep]

        log.info(
            "rerank_scores",
            min=min(scores), max=max(scores),
            spread=max(scores) - min(scores), n=len(scores),
        )
        ranked = sorted(zip(hits, scores, strict=True), key=lambda p: -p[1])
        return [h for h, _ in ranked[:keep]]
