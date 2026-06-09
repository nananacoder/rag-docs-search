from app.core.config import Settings
from app.services.retrieval.base import Retriever
from app.services.retrieval.discovery_engine import DiscoveryEngineRetriever
from app.services.retrieval.mock import MockRetriever


def build_retriever(settings: Settings) -> Retriever:
    match settings.retrieval_backend:
        case "mock":
            return MockRetriever()
        case "discovery_engine":
            if not (settings.gcp_project_id and settings.discovery_engine_engine_id):
                raise RuntimeError(
                    "discovery_engine backend requires GCP_PROJECT_ID and "
                    "DISCOVERY_ENGINE_ENGINE_ID",
                )
            return DiscoveryEngineRetriever(settings)
        case "pgvector":
            raise NotImplementedError("pgvector retriever lands in Phase 2")


__all__ = ["Retriever", "build_retriever"]
