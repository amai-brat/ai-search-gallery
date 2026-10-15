from datetime import datetime
from typing import Annotated

from dependencies import get_repository
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from repositories.image_repository import ImageRepository
from utils.ml_core import get_text_embedding

router = APIRouter(prefix="/images/search", tags=["images"])


class SearchHit(BaseModel):
    id: int
    score: float
    filepath: str
    sha256sum: str
    added_at: datetime


class SearchResponse(BaseModel):
    results: list[SearchHit]


@router.get("", response_model=SearchResponse)
def semantic_search(
    repo: Annotated[ImageRepository, Depends(get_repository)],
    semantic_query: Annotated[str | None, Query(alias="semanticQuery")] = None,
    ocr_query: Annotated[str | None, Query(alias="ocrQuery")] = None,
    limit: Annotated[int, Query(ge=1, le=100, alias="limit")] = 20,
) -> SearchResponse:
    results = []
    if semantic_query:
        vector = get_text_embedding(semantic_query)
        results.extend(
            [
                SearchHit(
                    id=x.image.id,  # type: ignore
                    score=x.distance,
                    filepath=x.image.filepath,
                    sha256sum=x.image.sha256sum,
                    added_at=x.image.added_at,
                )
                for x in repo.nearest_(vector, limit=limit)
            ]
        )
    return SearchResponse(results=results)
