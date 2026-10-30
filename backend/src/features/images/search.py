from datetime import datetime
from typing import Annotated, Literal

from dependencies import get_repository
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from repositories.image_repository import ImageRepository
from utils.config import (
    SEMANTIC_WINDOW_BALANCED,
    SEMANTIC_WINDOW_STRICT,
    SEMANTIC_WINDOW_WIDE,
)
from utils.ml_core import get_text_embedding
from utils.search_query import QuerySyntaxError

router = APIRouter(prefix="/images/search", tags=["images"])


class SearchHit(BaseModel):
    id: int
    score: float | None = Field(
        default=None,
        description=(
            "Cosine distance for semantic hits. OCR-only hits have no distance "
            "and therefore no score."
        ),
    )
    matched_by: list[Literal["semantic", "ocr"]]
    filepath: str
    sha256sum: str
    added_at: datetime
    ocr_text: str | None = None


Strictness = Literal["strict", "balanced", "wide", "off"]

# How far from the best semantic hit (cosine distance) a result may be.
_WINDOWS: dict[str, float | None] = {
    "strict": SEMANTIC_WINDOW_STRICT,
    "balanced": SEMANTIC_WINDOW_BALANCED,
    "wide": SEMANTIC_WINDOW_WIDE,
    "off": None,
}


class SearchResponse(BaseModel):
    results: list[SearchHit]
    hidden_count: int = Field(
        default=0,
        description=(
            "Semantic hits dropped as too far from the best one. "
            "Always 0 with strictness=off."
        ),
    )


@router.get("", response_model=SearchResponse)
def search(
    repo: Annotated[ImageRepository, Depends(get_repository)],
    semantic_query: Annotated[str | None, Query(alias="semanticQuery")] = None,
    ocr_query: Annotated[str | None, Query(alias="ocrQuery")] = None,
    limit: Annotated[int, Query(ge=1, le=100, alias="limit")] = 20,
    strictness: Annotated[Strictness, Query(alias="strictness")] = "balanced",
) -> SearchResponse:
    """Search images by CLIP similarity and/or text recognized by OCR.

    ``ocrQuery`` supports a Kibana-like syntax: ``AND``, ``OR``, ``NOT``,
    quoted phrases and parentheses. Adjacent terms are combined with AND.
    Each search mode returns at most ``limit`` hits; images matching both modes
    are returned once with both values in ``matched_by``.

    Semantic hits are always the nearest neighbours, relevant or not, so
    ``strictness`` drops those that are noticeably farther from the query than the
    best hit (``off`` keeps everything).
    """
    semantic_query = semantic_query.strip() if semantic_query else None
    ocr_query = ocr_query.strip() if ocr_query else None

    hits: dict[int, SearchHit] = {}
    hidden_count = 0

    if semantic_query:
        vector = get_text_embedding(semantic_query)
        nearest = repo.nearest_(vector, limit=limit)
        window = _WINDOWS[strictness]
        if window is not None and nearest:
            threshold = nearest[0].distance + window
            kept = [h for h in nearest if h.distance <= threshold]
            hidden_count = len(nearest) - len(kept)
            nearest = kept
        for hit in nearest:
            image = hit.image
            if image.id is None:
                continue
            hits[image.id] = SearchHit(
                id=image.id,
                score=hit.distance,
                matched_by=["semantic"],
                filepath=image.filepath,
                sha256sum=image.sha256sum,
                added_at=image.added_at,
                ocr_text=image.ocr_text,
            )

    if ocr_query:
        try:
            ocr_images = repo.search_ocr(ocr_query, limit=limit)
        except QuerySyntaxError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        for image in ocr_images:
            image_id = image.id
            if image_id is None:
                continue
            existing = hits.get(image_id)
            if existing is not None:
                existing.matched_by.append("ocr")
                continue
            hits[image_id] = SearchHit(
                id=image_id,
                matched_by=["ocr"],
                filepath=image.filepath,
                sha256sum=image.sha256sum,
                added_at=image.added_at,
                ocr_text=image.ocr_text,
            )

    return SearchResponse(results=list(hits.values()), hidden_count=hidden_count)
