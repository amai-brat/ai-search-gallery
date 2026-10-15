from datetime import datetime
from typing import Annotated

from dependencies import get_repository
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from repositories.image_repository import ImageRepository

router = APIRouter(prefix="/images", tags=["images"])


class ImageResponse(BaseModel):
    id: int | None
    sha256sum: str
    filepath: str
    added_at: datetime


class ListImagesResponse(BaseModel):
    results: list[ImageResponse]


@router.get("", response_model=ListImagesResponse)
def list_images(
    repo: Annotated[ImageRepository, Depends(get_repository)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> ListImagesResponse:
    offset = (page - 1) * page_size
    rows = repo.get_all(offset, page_size)
    return ListImagesResponse(
        results=[
            ImageResponse(
                id=r.id, sha256sum=r.sha256sum, filepath=r.filepath, added_at=r.added_at
            )
            for r in rows
        ]
    )
