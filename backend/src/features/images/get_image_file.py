import mimetypes
from pathlib import Path
from typing import Annotated

from dependencies import get_repository
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from PIL import Image as PILImage
from PIL import ImageOps
from repositories.image_repository import ImageRepository
from utils.config import STORAGE_DIR

router = APIRouter(prefix="/images", tags=["images"])

THUMBNAILS_DIR = STORAGE_DIR / "thumbnails"


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
        # Show the image in the browser (and in Swagger) instead of downloading it.
        content_disposition_type="inline",
    )


@router.get("/{image_id}/thumbnail", response_class=FileResponse)
def get_image_thumbnail(
    image_id: Annotated[int, PathParam(ge=1)],
    repo: Annotated[ImageRepository, Depends(get_repository)],
    size: Annotated[int, Query(ge=64, le=1600)] = 480,
) -> FileResponse:
    """Downscaled WebP preview, cached on disk, for fast gallery grids."""
    image = repo.get(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    source = Path(image.filepath)
    if not source.is_file():
        raise HTTPException(status_code=404, detail="File missing on disk")

    thumb = THUMBNAILS_DIR / f"{image.sha256sum}_{size}.webp"
    if not thumb.is_file():
        THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with PILImage.open(source) as img:
                img = ImageOps.exif_transpose(img)
                img.thumbnail((size, size))
                img.convert("RGB").save(thumb, "WEBP", quality=82)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=422, detail="Cannot create thumbnail"
            ) from exc

    return FileResponse(
        thumb,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
