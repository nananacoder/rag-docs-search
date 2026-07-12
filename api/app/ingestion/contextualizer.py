"""Contextual Retrieval prefix generation (learnings/10 Adoption 1).

Per chunk: one Gemini Flash call with the parent chapter as context,
asking for 50-100 tokens situating the chunk. Prompts are ordered
[chapter][chunk] so Gemini's implicit prompt caching amortizes the
chapter tokens across all its chunks (~$3 one-time at our corpus size).
"""

from google import genai
from google.genai import types

from app.core.config import Settings
from app.core.logging import get_logger

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

    async def contextualize(self, chunk_text: str, chapter_text: str) -> str:
        response = await self._client.aio.models.generate_content(
            model=self.settings.gemini_model,
            contents=_PROMPT.format(chapter_text=chapter_text, chunk_text=chunk_text),
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=160),
        )
        return (response.text or "").strip()
