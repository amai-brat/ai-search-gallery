"""Indexer: a child process of the app that computes CLIP vectors and OCR text.

The queue is the index_jobs table: the API inserts a 'queued' row, the indexer
claims it, walks the folder and writes every image to the images table. The
heavy work runs in its own process, so a crash in native code (ONNX Runtime,
OpenCV) cannot take the API down and the API stays responsive while indexing.
``IndexerSupervisor`` (used by the app) starts the process and restarts it if
it dies; jobs interrupted that way are queued again and resume.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import threading
import time
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg", ".webp")
IDLE_POLL_S = 1.0


def list_images(directory_path: str) -> list[str]:
    return sorted(
        os.path.join(root, file)
        for root, _, files in os.walk(directory_path)
        for file in files
        if file.lower().endswith(SUPPORTED_FORMATS)
    )


# --------------------------------------------------------------- child process


def _parent_alive() -> bool:
    """False once the app process is gone (e.g. killed), so the indexer does
    not outlive it. Its job is then resumed on the next start."""
    parent = multiprocessing.parent_process()
    return parent is None or parent.is_alive()


def run() -> None:
    """Entry point of the indexer process."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s indexer %(levelname)s %(message)s"
    )
    from repositories.index_job_repository import IndexJobRepository
    from utils.database import get_db_connection

    with get_db_connection() as conn:
        resumed = IndexJobRepository(conn).requeue_interrupted()
    if resumed:
        logger.info("Resuming %d interrupted job(s)", resumed)
    logger.info("Indexer started (pid %d)", os.getpid())

    while _parent_alive():
        with get_db_connection() as conn:
            job = IndexJobRepository(conn).claim_next()
        if job is None:
            time.sleep(IDLE_POLL_S)
            continue
        _run_job(job.id, job.directory_path)
    logger.info("App process is gone, indexer exits")


def _run_job(job_id: int, directory_path: str) -> None:
    from repositories.index_job_repository import IndexJobRepository
    from utils.database import get_db_connection

    logger.info("Job %d: %s", job_id, directory_path)
    error = None
    try:
        files = list_images(directory_path)
        with get_db_connection() as conn:
            IndexJobRepository(conn).set_total(job_id, len(files))
        _index_files(files, job_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("Job %d failed", job_id)
        error = str(e) or type(e).__name__
    with get_db_connection() as conn:
        IndexJobRepository(conn).finish(job_id, error=error)
    logger.info("Job %d finished%s", job_id, f" with error: {error}" if error else "")


def _report(job_id: int, **counters: int) -> None:
    """Persist job progress; never let a bookkeeping error break indexing."""
    from repositories.index_job_repository import IndexJobRepository
    from utils.database import get_db_connection

    try:
        with get_db_connection() as conn:
            IndexJobRepository(conn).add_progress(job_id, **counters)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not update index job %s: %s", job_id, e)


def _index_files(files: list[str], job_id: int) -> None:
    from models.image import ImageCreate
    from repositories.image_repository import ImageRepository
    from utils.checksums import sha256sum
    from utils.database import get_db_connection
    from utils.ml_core import get_image_embedding
    from utils.ocr import get_image_text

    for filepath in files:
        if not _parent_alive():
            logger.info("App process is gone, indexer exits")
            raise SystemExit(0)
        try:
            checksum = sha256sum(filepath)
            with get_db_connection() as conn:
                existing = ImageRepository(conn).get_by_sha256(checksum)
            if (
                existing is not None
                and existing.embedding is not None
                and existing.ocr_text is not None
            ):
                if existing.filepath != filepath:
                    # Same picture under a new path: keep the path current.
                    with get_db_connection() as conn:
                        ImageRepository(conn).upsert(
                            ImageCreate(
                                sha256sum=checksum,
                                filepath=filepath,
                                added_at=existing.added_at,
                                embedding=None,
                            )
                        )
                _report(job_id, skipped=1)
                continue

            # Reuse whatever is already stored, so a partial index can be
            # completed without redoing expensive work.
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
                    # OCR must not prevent the image from being searchable by
                    # meaning; the next run retries it.
                    logger.warning("OCR failed for %s: %s", filepath, e)
                    ocr_text = None

            with get_db_connection() as conn:
                ImageRepository(conn).upsert(
                    ImageCreate(
                        sha256sum=checksum,
                        filepath=filepath,
                        added_at=datetime.now(UTC),
                        embedding=embedding,
                        ocr_text=ocr_text,
                    )
                )
            _report(job_id, indexed=1)
        except Exception as e:  # noqa: BLE001
            logger.warning("Error processing %s: %s", filepath, e)
            _report(job_id, failed=1)


# ---------------------------------------------------------------- app process


class IndexerSupervisor:
    """Starts the indexer process and restarts it if it exits unexpectedly."""

    CHECK_S = 2.0
    MAX_BACKOFF_S = 60.0

    def __init__(self) -> None:
        self._ctx = multiprocessing.get_context("spawn")
        self._process: multiprocessing.process.BaseProcess | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = 0.0

    def start(self) -> None:
        self._spawn()
        self._thread = threading.Thread(
            target=self._watch, name="indexer-supervisor", daemon=True
        )
        self._thread.start()

    def _spawn(self) -> None:
        self._process = self._ctx.Process(target=run, name="indexer", daemon=True)
        self._process.start()
        self._started_at = time.monotonic()
        logger.info("Indexer process started (pid %s)", self._process.pid)

    def _watch(self) -> None:
        backoff = 1.0
        while not self._stop.wait(self.CHECK_S):
            process = self._process
            if process is None or process.is_alive():
                # A process that has run for a while is healthy again; one that
                # keeps crashing on start is restarted less and less often.
                if time.monotonic() - self._started_at > self.MAX_BACKOFF_S:
                    backoff = 1.0
                continue
            logger.warning(
                "Indexer process exited (code %s), restarting in %.0f s",
                process.exitcode,
                backoff,
            )
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, self.MAX_BACKOFF_S)
            self._spawn()

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=10)

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process else None
