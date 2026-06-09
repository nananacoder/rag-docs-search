from fastapi import APIRouter

from app.api.deps import RetrieverDep
from app.models.book import Book

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=list[Book])
async def list_books(retriever: RetrieverDep) -> list[Book]:
    return await retriever.list_books()
