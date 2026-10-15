from contextlib import asynccontextmanager

from fastapi import FastAPI
from features.images import get_image_file, indexing, list_images, search
from migrate import run_migrations
from utils.database import open_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    open_pool()
    yield


app = FastAPI(title="AI Search Gallery", lifespan=lifespan)

app.include_router(list_images.router)
app.include_router(get_image_file.router)
app.include_router(indexing.router)
app.include_router(search.router)
