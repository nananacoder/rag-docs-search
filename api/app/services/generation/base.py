from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.models.citation import RetrievedChunk


@dataclass(slots=True)
class GenerationMetrics:
    input_tokens: int
    output_tokens: int
    model: str


class Generator(ABC):
    @abstractmethod
    def stream(
        self,
        question: str,
        context: list[RetrievedChunk],
    ) -> AsyncIterator[str]:
        """Yield answer tokens/chunks as they arrive."""

    @abstractmethod
    def last_metrics(self) -> GenerationMetrics:
        """Metrics for the most recently-completed stream."""
