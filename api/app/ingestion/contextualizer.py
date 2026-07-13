"""Contextual Retrieval prefix generation (learnings/10 Adoption 1).

Per chunk: one Gemini Flash call with the parent chapter as context,
asking for 50-100 tokens situating the chunk. Prompts are ordered
[chapter][chunk] so Gemini's implicit prompt caching amortizes the
chapter tokens across all its chunks (~$3 one-time at our corpus size).
"""

import hashlib

from google import genai
from google.genai import types

from app.core.config import Settings
from app.core.logging import get_logger
from app.ingestion.backoff import llm_retry
from app.ingestion.cache import JsonCache

log = get_logger(__name__)

_PROMPT = (
    "<document>\n{chapter_text}\n</document>\n\n"
    "Here is the chunk we want to situate within the document above:\n"
    "<chunk>\n{chunk_text}\n</chunk>\n\n"
    "Give a short succinct context (50-100 tokens) to situate this chunk "
    "within the overall document for the purposes of improving search "
    "retrieval of the chunk. Mention the chapter and topic it belongs to. "
    "Answer only with the succinct context and nothing else."
)


class Contextualizer:
    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self.settings = settings
        self._client = client or genai.Client(
            vertexai=True, project=settings.gcp_project_id, location=settings.gcp_location
        )
        self._cache = JsonCache(settings.ingest_cache_dir, "contexts")

    async def contextualize(self, chunk_text: str, chapter_text: str) -> str:
        raw = f"{self.settings.gemini_model}:{chapter_text[:2000]}:{chunk_text}"
        key = hashlib.sha256(raw.encode()).hexdigest()
        if (hit := self._cache.get(key)) is not None:
            return str(hit)
        text = await self._generate(chunk_text, chapter_text)
        self._cache.set(key, text)
        return text

    @llm_retry
    async def _generate(self, chunk_text: str, chapter_text: str) -> str:
        response = await self._client.aio.models.generate_content(
            model=self.settings.gemini_model,
            contents=_PROMPT.format(chapter_text=chapter_text, chunk_text=chunk_text),
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=160),
        )
        return (response.text or "").strip()
