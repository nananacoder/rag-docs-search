from abc import ABC, abstractmethod

from app.models.book import Book
from app.models.citation import RetrievedChunk


class Retriever(ABC):
    """Backend-agnostic retrieval interface.

    Implementations: MockRetriever (no GCP), DiscoveryEngineRetriever (Phase 1),
    PgVectorRetriever (Phase 2).
    """

    @abstractmethod
    async def list_books(self) -> list[Book]:
        """Return the full library catalog."""

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int,
        book_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Return top-k chunks, optionally scoped to a subset of books."""
