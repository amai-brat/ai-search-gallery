from fastapi import APIRouter
from pydantic import BaseModel
from worker import index_images_task

router = APIRouter(prefix="/images/index", tags=["images"])


class IndexRequest(BaseModel):
    directory_path: str


class IndexResponse(BaseModel):
    task_id: str
    status: str
    directory_path: str


@router.post("", response_model=IndexResponse)
def trigger_indexing(req: IndexRequest) -> IndexResponse:
    result = index_images_task.delay(req.directory_path)  # type: ignore
    return IndexResponse(
        task_id=result.id,
        status="queued",
        directory_path=req.directory_path,
    )
