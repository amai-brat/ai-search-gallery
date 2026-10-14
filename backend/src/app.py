from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from migrate import run_migrations
from pydantic import BaseModel
from repositories.image_repository import ImageRepository
from utils.database import get_db_connection, open_pool
from utils.ml_core import get_text_embedding
from worker import index_images_task


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    open_pool()
    yield


app = FastAPI(title="AI Search Gallery", lifespan=lifespan)


def get_repository():
    with get_db_connection() as conn:
        yield ImageRepository(conn)


class IndexRequest(BaseModel):
    directory_path: str


class SearchRequest(BaseModel):
    semantic_query: str | None
    ocr_query: str | None
    limit: int = 5


@app.post("/index")
def trigger_indexing(req: IndexRequest):
    index_images_task.delay(req.directory_path)  # type: ignore
    return {
        "message": f"Background indexing started for directory: {req.directory_path}"
    }


@app.post("/search")
def semantic_search(
    req: SearchRequest, repo: Annotated[ImageRepository, Depends(get_repository)]
):
    results = []
    if req.semantic_query:
        query_vector = get_text_embedding(req.semantic_query)
        results.extend(repo.nearest(query_vector, limit=req.limit))

    return {"results": results}
