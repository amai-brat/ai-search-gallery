import mimetypes
from pathlib import Path
from typing import Annotated

from dependencies import get_repository
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from repositories.image_repository import ImageRepository

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/{image_id}/file", response_class=FileResponse)
def get_image_file(
    image_id: Annotated[int, PathParam(ge=1)],
    repo: Annotated[ImageRepository, Depends(get_repository)],
) -> FileResponse:
    image = repo.get(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    path = Path(image.filepath)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File missing on disk")

    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=path.name,
    )
