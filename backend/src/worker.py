import os

import dotenv

env_file = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))), ".env"
)
dotenv.load_dotenv(env_file)

import logging
from datetime import UTC, datetime

from celery import Celery
from celery.signals import worker_process_init
from models.image import ImageCreate
from repositories.image_repository import ImageRepository
from repositories.index_job_repository import IndexJobRepository
from utils.checksums import sha256sum
from utils.config import CELERY_BROKER
from utils.database import db_pool, get_db_connection
from utils.ml_core import get_image_embedding
from utils.ocr import get_image_text

celery_app = Celery(
    "worker",
    broker=CELERY_BROKER,
    backend=CELERY_BROKER,
)

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg", ".webp")


@worker_process_init.connect
def _init_worker(**kwargs):
    db_pool.open()
    # A freshly started worker cannot be running anything: jobs still marked
    # as running belong to a worker that died.
    try:
        with get_db_connection() as conn:
            IndexJobRepository(conn).fail_stale("Воркер был перезапущен")
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not reset stale index jobs: %s", e)


def _report(job_id: int | None, **counters: int) -> None:
    """Persist job progress; never let a bookkeeping error break indexing."""
    if job_id is None:
        return
    try:
        with get_db_connection() as conn:
            IndexJobRepository(conn).add_progress(job_id, **counters)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not update index job %s: %s", job_id, e)


@celery_app.task
def index_images_task(directory_path: str, job_id: int | None = None):
    files_to_index = [
        os.path.join(root, file)
        for root, _, files in os.walk(directory_path)
        for file in files
        if file.lower().endswith(SUPPORTED_FORMATS)
    ]

    if job_id is not None:
        with get_db_connection() as conn:
            IndexJobRepository(conn).mark_running(job_id, len(files_to_index))

    try:
        _index_files(files_to_index, job_id)
    except Exception as e:  # noqa: BLE001
        if job_id is not None:
            with get_db_connection() as conn:
                IndexJobRepository(conn).finish(job_id, error=str(e))
        raise

    if job_id is not None:
        with get_db_connection() as conn:
            IndexJobRepository(conn).finish(job_id)


def _index_files(files_to_index: list[str], job_id: int | None) -> None:
    for filepath in files_to_index:
        try:
            checksum = sha256sum(filepath)

            # 1. Short transaction: check if we already have it.
            with get_db_connection() as conn:
                existing = ImageRepository(conn).get_by_sha256(checksum)
            if (
                existing is not None
                and existing.embedding is not None
                and existing.ocr_text is not None
            ):
                logger.info("Skipping (already indexed): %s", filepath)
                _report(job_id, skipped=1)
                continue

            # 2. Heavy compute, NO connection held. Reuse whatever is
            # already in the database so partial indexes can be completed
            # without redoing expensive work.
            if existing is not None and existing.embedding is not None:
                embedding = existing.embedding
            else:
                embedding = get_image_embedding(filepath)

            if existing is not None and existing.ocr_text is not None:
                ocr_text = existing.ocr_text
            else:
                try:
                    ocr_text = get_image_text(filepath)
                except Exception as e:  # noqa: BLE001
                    # OCR should not prevent the image from being indexed
                    # semantically; the next run will retry it.
                    logger.warning("OCR failed for %s: %s", filepath, e)
                    ocr_text = None

            # 3. Short transaction: upsert.
            with get_db_connection() as conn, conn.transaction():
                ImageRepository(conn).upsert(
                    ImageCreate(
                        sha256sum=checksum,
                        filepath=filepath,
                        added_at=datetime.now(UTC),
                        embedding=embedding,
                        ocr_text=ocr_text,
                    )
                )

            logger.info("Indexed: %s", filepath)
            _report(job_id, indexed=1)
        except Exception as e:  # noqa: BLE001
            # Pool context manager already rolled back on exception.
            logger.warning("Error processing %s: %s", filepath, e)
            _report(job_id, failed=1)
