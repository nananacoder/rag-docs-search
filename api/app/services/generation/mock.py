"""Deterministic generator for local dev — no LLM calls, fast."""

import asyncio
from collections.abc import AsyncIterator

from app.models.citation import RetrievedChunk
from app.services.generation.base import GenerationMetrics, Generator


class MockGenerator(Generator):
    def __init__(self) -> None:
        self._metrics = GenerationMetrics(input_tokens=0, output_tokens=0, model="mock")

    async def stream(
        self,
        question: str,
        context: list[RetrievedChunk],
    ) -> AsyncIterator[str]:
        # Build a plausible answer that cites each retrieved chunk by index.
        cite_refs = " ".join(f"[{i + 1}]" for i, _ in enumerate(context))
        base = context[0].content if context else "No context was retrieved."
        snippet = base[:180] + ("..." if len(base) > 180 else "")
        answer = (
            f"Based on the retrieved sources, here is a synthesized answer to the question "
            f'"{question}".\n\n'
            f"{snippet} {cite_refs}\n\n"
            f"This is a mock response; swap RETRIEVAL_BACKEND to `discovery_engine` to see real generation."
        )

        # Emit one token every ~20ms to simulate streaming in the UI.
        for word in answer.split(" "):
            yield word + " "
            await asyncio.sleep(0.02)

        self._metrics = GenerationMetrics(
            input_tokens=sum(len(c.content.split()) for c in context),
            output_tokens=len(answer.split()),
            model="mock",
        )

    def last_metrics(self) -> GenerationMetrics:
        return self._metrics
