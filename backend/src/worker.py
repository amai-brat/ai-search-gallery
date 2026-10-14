import logging
import os
from datetime import UTC, datetime

from celery import Celery
from celery.signals import worker_process_init
from models.image import ImageCreate
from repositories.image_repository import ImageRepository
from utils.checksums import sha256sum
from utils.config import CELERY_BROKER
from utils.database import db_pool, get_db_connection
from utils.ml_core import get_image_embedding

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


@celery_app.task
def index_images_task(directory_path: str):
    for root, _, files in os.walk(directory_path):
        for file in files:
            if not file.lower().endswith(SUPPORTED_FORMATS):
                continue

            filepath = os.path.join(root, file)
            try:
                checksum = sha256sum(filepath)

                # 1. Short transaction: check if we already have it.
                with get_db_connection() as conn:
                    existing = ImageRepository(conn).get_by_sha256(checksum)
                    if existing is not None and existing.embedding is not None:
                        logger.info("Skipping (already indexed): %s", filepath)
                        continue

                # 2. Heavy compute, NO connection held.
                embedding = get_image_embedding(filepath)

                # 3. Short transaction: upsert.
                with get_db_connection() as conn, conn.transaction():
                    ImageRepository(conn).upsert(
                        ImageCreate(
                            sha256sum=checksum,
                            filepath=filepath,
                            added_at=datetime.now(UTC),
                            embedding=embedding,
                            ocr_text=None,
                        )
                    )

                logger.info("Indexed: %s", filepath)
            except Exception as e:  # noqa: BLE001
                # Pool context manager already rolled back on exception.
                logger.warning("Error processing %s: %s", filepath, e)
