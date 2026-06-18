"""Phase 1 retriever backed by Vertex AI Search (Agent Builder / Discovery Engine).

Uses the regional Discovery Engine endpoint (us / eu / global) via the
synchronous SearchServiceClient. The sync client is wrapped in asyncio.to_thread
because the async (grpc-asyncio) client conflicts with FastAPI's worker-thread
dependency injection — it tries to bind to an event loop at construction time
in a thread that has none. See learnings/07 for the full diagnosis.

Maps Discovery Engine search results into the project's RetrievedChunk shape
so the rest of the API doesn't change.
"""

from __future__ import annotations

import asyncio

from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine_v1

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.book import Book
from app.models.citation import RetrievedChunk
from app.services.retrieval.base import Retriever

log = get_logger(__name__)


class DiscoveryEngineRetriever(Retriever):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.gcp_project_id:
            raise ValueError("GCP_PROJECT_ID is required when RETRIEVAL_BACKEND=discovery_engine")
        if not settings.discovery_engine_engine_id:
            raise ValueError("DISCOVERY_ENGINE_ENGINE_ID is required")

        location = settings.discovery_engine_location
        client_options = (
            ClientOptions(api_endpoint=f"{location}-discoveryengine.googleapis.com")
            if location != "global"
            else None
        )
        self._client = discoveryengine_v1.SearchServiceClient(client_options=client_options)
        self._serving_config = (
            f"projects/{settings.gcp_project_id}"
            f"/locations/{location}"
            f"/collections/{settings.discovery_engine_collection}"
            f"/engines/{settings.discovery_engine_engine_id}"
            f"/servingConfigs/default_search"
        )

        log.info(
            "discovery_engine_retriever_init",
            project=settings.gcp_project_id,
            location=location,
            engine=settings.discovery_engine_engine_id,
            serving_config=self._serving_config,
        )

    async def list_books(self) -> list[Book]:
        # Phase 1: corpus is a single OpenStax textbook with a fixed catalog.
        # Hard-coded here so the UI's left pane works without a separate catalog DB.
        # In Phase 2 a real `books` table in Cloud SQL will replace this.
        return [
            Book(
                book_id="openstax-astronomy-2e",
                title="Astronomy 2e",
                author="Fraknoi, Morrison & Wolff (OpenStax)",
                year=2026,
                page_count=1151,
                gcs_uri="gs://my-rag-docs-bucket-123/astronomy-2e.pdf",
            ),
        ]

    async def retrieve(
        self,
        query: str,
        top_k: int,
        book_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        # Build search request. Snippet is a Standard-tier feature.
        # Extractive segments / extractive answers require Enterprise tier — not enabled
        # to keep Phase 1 cost down (see phase1-managed.md §3.3).
        request = discoveryengine_v1.SearchRequest(
            serving_config=self._serving_config,
            query=query,
            page_size=top_k,
            content_search_spec=discoveryengine_v1.SearchRequest.ContentSearchSpec(
                snippet_spec=discoveryengine_v1.SearchRequest.ContentSearchSpec.SnippetSpec(
                    return_snippet=True,
                ),
            ),
            query_expansion_spec=discoveryengine_v1.SearchRequest.QueryExpansionSpec(
                condition=discoveryengine_v1.SearchRequest.QueryExpansionSpec.Condition.AUTO,
            ),
        )

        log.info("discovery_engine_search", query_chars=len(query), top_k=top_k)
        # Sync client must run off the event loop thread.
        response = await asyncio.to_thread(self._client.search, request=request)

        chunks: list[RetrievedChunk] = []
        for i, result in enumerate(response.results):
            doc = result.document
            derived = dict(doc.derived_struct_data) if doc.derived_struct_data else {}

            # Standard tier returns snippets only (no extractive segments / page numbers).
            # Snippets come back as proto Value objects under derived_struct_data['snippets'].
            snippets = derived.get("snippets") or []

            content = ""
            if snippets:
                snip0 = dict(snippets[0])
                content = snip0.get("snippet", "") or ""

            # Fall back to the document title or name if no snippet surfaced
            if not content:
                content = derived.get("title", "") or doc.name

            # Standard tier does NOT expose page numbers — set to 1 as a placeholder.
            # Phase 2's self-built pipeline restores per-chunk page tracking.
            page = 1

            chunks.append(
                RetrievedChunk(
                    chunk_id=doc.id or f"result-{i}",
                    book_id="openstax-astronomy-2e",
                    book_title="Astronomy 2e",
                    author="Fraknoi, Morrison & Wolff (OpenStax)",
                    chapter_num=None,  # Vertex AI Search doesn't expose chapter — Phase 2 will
                    chapter_title=None,
                    page=page,
                    content=content,
                    score=float(result.model_scores.get("relevance", 0.0)) if result.model_scores else 0.0,
                    modality="text",
                ),
            )

        log.info("discovery_engine_search_complete", returned=len(chunks))
        return chunks
