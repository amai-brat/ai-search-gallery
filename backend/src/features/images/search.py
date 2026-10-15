from datetime import datetime
from typing import Annotated

from dependencies import get_repository
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from repositories.image_repository import ImageRepository
from utils.ml_core import get_text_embedding

router = APIRouter(prefix="/images/search", tags=["images"])


class SearchRequest(BaseModel):
    semantic_query: str | None = None
    ocr_query: str | None = None
    limit: int = 5


class SearchHit(BaseModel):
    id: int
    score: float
    filepath: str
    sha256sum: str
    added_at: datetime


class SearchResponse(BaseModel):
    results: list[SearchHit]


@router.post("", response_model=SearchResponse)
def semantic_search(
    req: SearchRequest,
    repo: Annotated[ImageRepository, Depends(get_repository)],
) -> SearchResponse:
    results = []
    if req.semantic_query:
        vector = get_text_embedding(req.semantic_query)
        results.extend(
            [
                SearchHit(x.id, 0, x.filepath, x.sha256sum, x.added_at)  # type: ignore
                for x in repo.nearest(vector, limit=req.limit)
            ]
        )
    return SearchResponse(results=results)
