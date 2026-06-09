from app.core.config import Settings
from app.services.generation.base import Generator
from app.services.generation.gemini import GeminiGenerator
from app.services.generation.mock import MockGenerator


def build_generator(settings: Settings) -> Generator:
    if settings.is_gcp_backend and settings.gcp_project_id:
        return GeminiGenerator(settings)
    return MockGenerator()


__all__ = ["Generator", "build_generator"]
