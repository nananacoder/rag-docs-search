"""Gemini Embedding 2 @ 768-dim (§4.4, learnings/10 Adoption 2).

- output_dimensionality=768: MRL truncation (pgvector HNSW caps at 2000)
- every vector is L2-normalized before storage — sources disagree on
  whether truncated outputs come pre-normalized; normalizing is idempotent
- cache keyed by sha256 of the EXACT text sent to the API + model + dim,
  so a regenerated context_prefix misses the cache as it must
- batches of <=250, exponential backoff on 429/503 via tenacity
"""

import hashlib
import math

from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.logging import get_logger
from app.ingestion.cache import JsonCache

log = get_logger(__name__)


def l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return vec if norm == 0 else [x / norm for x in vec]


def _is_retryable(exc: BaseException) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code in (429, 503)


class Embedder:
    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self.settings = settings
        self._client = client or genai.Client(
            vertexai=True, project=settings.gcp_project_id, location=settings.gcp_location
        )
        self._cache = JsonCache(settings.ingest_cache_dir, "embeddings")

    def _key(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> str:
        raw = (
            f"{self.settings.embedding_model}:{self.settings.embedding_dim}"
            f":{task_type}:{text}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    async def embed_query(self, query: str) -> list[float]:
        """Query-side embedding (RETRIEVAL_QUERY task type), cached (§5.3)."""
        key = self._key(query, "RETRIEVAL_QUERY")
        if (hit := self._cache.get(key)) is not None:
            return [float(x) for x in hit]
        vecs = await self._embed_batch([query], task_type="RETRIEVAL_QUERY")
        normalized = l2_normalize(vecs[0])
        self._cache.set(key, normalized)
        return normalized

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed contextualized texts; cache hits skip the API entirely."""
        out: list[list[float] | None] = [self._cache.get(self._key(t)) for t in texts]
        missing = [i for i, v in enumerate(out) if v is None]
        bs = self.settings.embedding_batch_size
        for start in range(0, len(missing), bs):
            batch_idx = missing[start : start + bs]
            vectors = await self._embed_batch([texts[i] for i in batch_idx])
            for i, vec in zip(batch_idx, vectors, strict=True):
                normalized = l2_normalize(vec)
                self._cache.set(self._key(texts[i]), normalized)
                out[i] = normalized
        log.info(
            "embedded", total=len(texts), cache_hits=len(texts) - len(missing),
            api_calls=len(missing),
        )
        return [v for v in out if v is not None]

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=2, max=60),
        stop=stop_after_attempt(6),
    )
    async def _embed_batch(
        self, texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> list[list[float]]:
        response = await self._client.aio.models.embed_content(
            model=self.settings.embedding_model,
            contents=texts,
            config=types.EmbedContentConfig(
                output_dimensionality=self.settings.embedding_dim,
                task_type=task_type,
            ),
        )
        assert response.embeddings is not None
        return [list(e.values or []) for e in response.embeddings]
