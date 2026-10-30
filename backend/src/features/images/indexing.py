import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from dependencies import get_index_job_repository
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from repositories.index_job_repository import IndexJob, IndexJobRepository
from utils.config import STORAGE_DIR
from worker import SUPPORTED_FORMATS, index_images_task

router = APIRouter(prefix="/images/index", tags=["indexing"])

UPLOADS_DIR = STORAGE_DIR / "uploads"


class IndexRequest(BaseModel):
    directory_path: str


class IndexResponse(BaseModel):
    task_id: str
    job_id: int
    status: str
    directory_path: str


class IndexJobResponse(BaseModel):
    id: int
    kind: str
    directory_path: str
    status: str
    total_files: int | None
    processed_files: int
    indexed_files: int
    skipped_files: int
    failed_files: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class IndexJobsResponse(BaseModel):
    results: list[IndexJobResponse]


def _enqueue(
    jobs: IndexJobRepository, directory_path: str, kind: str
) -> IndexResponse:
    job = jobs.create(directory_path, kind)
    result = index_images_task.delay(directory_path, job.id)  # type: ignore
    return IndexResponse(
        task_id=result.id,
        job_id=job.id,
        status="queued",
        directory_path=directory_path,
    )


@router.post("", response_model=IndexResponse)
def trigger_indexing(
    req: IndexRequest,
    jobs: Annotated[IndexJobRepository, Depends(get_index_job_repository)],
) -> IndexResponse:
    directory = req.directory_path.strip().strip('"')
    if not directory or not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail="Папка не найдена на диске")
    return _enqueue(jobs, directory, "folder")


@router.post("/upload", response_model=IndexResponse)
def upload_and_index(
    jobs: Annotated[IndexJobRepository, Depends(get_index_job_repository)],
    files: Annotated[list[UploadFile], File()],
) -> IndexResponse:
    """Save uploaded images into the storage folder and queue them for indexing."""
    images = [
        f for f in files if (f.filename or "").lower().endswith(SUPPORTED_FORMATS)
    ]
    if not images:
        raise HTTPException(
            status_code=400,
            detail=f"Нет подходящих файлов. Поддерживаются: {', '.join(SUPPORTED_FORMATS)}",
        )

    batch_dir = UPLOADS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    for upload in images:
        # Browsers may send relative paths for folders; keep only the file name.
        name = Path((upload.filename or "image").replace("\\", "/")).name
        target = batch_dir / name
        n = 1
        while target.exists():
            target = batch_dir / f"{Path(name).stem}-{n}{Path(name).suffix}"
            n += 1
        with open(target, "wb") as out:
            while chunk := upload.file.read(1024 * 1024):
                out.write(chunk)

    return _enqueue(jobs, str(batch_dir), "upload")


@router.get("/jobs", response_model=IndexJobsResponse)
def list_jobs(
    jobs: Annotated[IndexJobRepository, Depends(get_index_job_repository)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> IndexJobsResponse:
    return IndexJobsResponse(
        results=[_to_response(j) for j in jobs.list(limit)],
    )


def _to_response(job: IndexJob) -> IndexJobResponse:
    return IndexJobResponse(**job.model_dump())
