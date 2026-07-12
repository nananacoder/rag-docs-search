"""Figure/diagram captioning via Gemini Vision (§4.3).

Captions are cached keyed by sha256(image_bytes) — re-ingests are free.
Caption text becomes the chunk content, embedded + BM25-indexed like text.
"""

import hashlib

from google import genai
from google.genai import types

from app.core.config import Settings
from app.core.logging import get_logger
from app.ingestion.cache import JsonCache

log = get_logger(__name__)

_PROMPT = (
    "This is a figure from an introductory astronomy textbook. Describe it "
    "in detail, including any axis labels, scientific quantities shown, "
    "celestial objects depicted, and explanatory annotations. If it is a "
    "diagram (e.g. H-R diagram, electromagnetic spectrum, galaxy "
    "classification chart), describe the structure and what each axis or "
    "region represents. Output only the description."
)


class Captioner:
    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self.settings = settings
        self._client = client or genai.Client(
            vertexai=True, project=settings.gcp_project_id, location=settings.gcp_location
        )
        self._cache = JsonCache(settings.ingest_cache_dir, "captions")

    async def caption(self, image_bytes: bytes) -> str:
        key = hashlib.sha256(image_bytes).hexdigest()
        if (hit := self._cache.get(key)) is not None:
            return str(hit)
        response = await self._client.aio.models.generate_content(
            model=self.settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                _PROMPT,
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        text: str = (response.text or "").strip()
        self._cache.set(key, text)
        return text
