"""Gemini-backed generator using google-genai in Vertex mode.

Streams tokens to the API SSE response. Captures usage_metadata for cost /
token-count logging.
"""

from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.citation import RetrievedChunk
from app.services.generation.base import GenerationMetrics, Generator

log = get_logger(__name__)


SYSTEM_PROMPT = (
    "You are a research assistant grounding every claim in the provided context.\n"
    "\n"
    "Response guidance — pick the appropriate mode for each question:\n"
    "\n"
    "MODE A — Full answer. The context fully answers the question. Answer "
    "directly with [n] inline citations.\n"
    "\n"
    "MODE B — Partial answer. The context answers part of the question but "
    "not all of it. Share what IS in the context with [n] citations, then "
    "explicitly state what specific part is NOT in the provided sources. "
    "Example: \"The context says X [1], but does not specify Y.\"\n"
    "\n"
    "MODE C — Not found. The context contains no relevant information. "
    "Say: \"I don't find this in the sources.\" and (when possible) briefly "
    "describe what topic the retrieved context DID cover, so the user knows "
    "the retrieval may have missed.\n"
    "\n"
    "Strict rules:\n"
    "1. Cite every factual claim with [n], where n is the 1-indexed passage number.\n"
    "2. Quote or closely paraphrase the source. Do not speculate or use outside knowledge.\n"
    "3. Prefer Mode B over Mode C when the context is even partially relevant — "
    "users prefer a partial answer that names its limits over a flat refusal.\n"
    "4. Always end your response with the attribution: \"Access for free at openstax.org\""
)


def build_user_prompt(question: str, context: list[RetrievedChunk]) -> str:
    blocks: list[str] = []
    for i, c in enumerate(context, start=1):
        header = f"[{i}] From {c.author}, {c.book_title}"
        if c.chapter_num is not None:
            ch_title = f': "{c.chapter_title}"' if c.chapter_title else ""
            header += f", Ch. {c.chapter_num}{ch_title}"
        header += f", p. {c.page}:"
        blocks.append(f"{header}\n{c.content}")
    context_block = "\n\n".join(blocks) if blocks else "(no context retrieved)"
    return f"Context:\n\n{context_block}\n\nQuestion: {question}"


class GeminiGenerator(Generator):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._metrics = GenerationMetrics(
            input_tokens=0, output_tokens=0, model=settings.gemini_model,
        )
        self._client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )
        log.info(
            "gemini_generator_init",
            model=settings.gemini_model,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )

    async def stream(
        self,
        question: str,
        context: list[RetrievedChunk],
    ) -> AsyncIterator[str]:
        prompt = build_user_prompt(question, context)
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=self.settings.generation_temperature,
        )

        last_chunk = None
        async for chunk in await self._client.aio.models.generate_content_stream(
            model=self.settings.gemini_model,
            contents=prompt,
            config=config,
        ):
            last_chunk = chunk
            if chunk.text:
                yield chunk.text

        # Capture token counts from the final chunk's usage_metadata
        if last_chunk and last_chunk.usage_metadata:
            um = last_chunk.usage_metadata
            self._metrics = GenerationMetrics(
                input_tokens=um.prompt_token_count or 0,
                output_tokens=um.candidates_token_count or 0,
                model=self.settings.gemini_model,
            )

    def last_metrics(self) -> GenerationMetrics:
        return self._metrics
