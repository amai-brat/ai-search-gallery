import logging
import threading
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from features.fs import pick_directory
from features.images import get_image_file, indexing, list_images, search
from migrate import run_migrations
from utils.config import CORS_ORIGINS, FRONTEND_DIST, INDEXER_ENABLED
from utils.ml_core import get_text_embedding
from utils.vector_index import vector_index

logger = logging.getLogger(__name__)


def _warm_up() -> None:
    # Load the stored vectors and the CLIP text encoder in the background so
    # the first search is fast.
    try:
        vector_index.refresh()
        logger.info("Vector index: %d images", len(vector_index))
        get_text_embedding("warm up")
    except Exception as e:  # noqa: BLE001
        logger.warning("Search warm-up failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    supervisor = None
    if INDEXER_ENABLED:
        from indexer import IndexerSupervisor

        supervisor = IndexerSupervisor()
        supervisor.start()
    threading.Thread(target=_warm_up, daemon=True).start()
    try:
        yield
    finally:
        if supervisor is not None:
            supervisor.stop()


app = FastAPI(title="AI Search Gallery", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(list_images.router)
api.include_router(get_image_file.router)
api.include_router(indexing.router)
api.include_router(search.router)
api.include_router(pick_directory.router)


@api.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api)

# The built frontend (npm run build); in development the Vite dev server is
# used instead and proxies /api here.
if (FRONTEND_DIST / "index.html").is_file():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    logger.warning(
        "No built frontend in %s: run `npm run build` in frontend/ "
        "(the API works without it, see /docs)",
        FRONTEND_DIST,
    )
