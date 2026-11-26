import sqlite3
from datetime import datetime

from pydantic import BaseModel
from utils.database import now

_COLUMNS = """
    id, kind, directory_path, status, total_files, processed_files,
    indexed_files, skipped_files, failed_files, error,
    created_at, started_at, finished_at
"""


class IndexJob(BaseModel):
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


def _job(row: sqlite3.Row) -> IndexJob:
    return IndexJob.model_validate(dict(row))


class IndexJobRepository:
    """Indexing jobs; the table is also the queue the indexer process takes
    work from (status 'queued' -> 'running' -> 'done' / 'failed')."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, directory_path: str, kind: str = "folder") -> IndexJob:
        row = self._conn.execute(
            f"""
            INSERT INTO index_jobs (directory_path, kind, created_at)
            VALUES (?, ?, ?)
            RETURNING {_COLUMNS}
            """,
            (directory_path, kind, now()),
        ).fetchone()
        return _job(row)

    def list(self, limit: int = 50) -> list[IndexJob]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM index_jobs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_job(r) for r in rows]

    def claim_next(self) -> IndexJob | None:
        """Take the oldest queued job and mark it running (atomically)."""
        row = self._conn.execute(
            f"""
            UPDATE index_jobs
            SET status = 'running', started_at = ?
            WHERE id = (
                SELECT id FROM index_jobs WHERE status = 'queued' ORDER BY id LIMIT 1
            )
            RETURNING {_COLUMNS}
            """,
            (now(),),
        ).fetchone()
        return _job(row) if row else None

    def set_total(self, job_id: int, total_files: int) -> None:
        self._conn.execute(
            "UPDATE index_jobs SET total_files = ? WHERE id = ?", (total_files, job_id)
        )

    def add_progress(
        self, job_id: int, *, indexed: int = 0, skipped: int = 0, failed: int = 0
    ) -> None:
        self._conn.execute(
            """
            UPDATE index_jobs
            SET processed_files = processed_files + ? + ? + ?,
                indexed_files = indexed_files + ?,
                skipped_files = skipped_files + ?,
                failed_files = failed_files + ?
            WHERE id = ?
            """,
            (indexed, skipped, failed, indexed, skipped, failed, job_id),
        )

    def finish(self, job_id: int, error: str | None = None) -> None:
        self._conn.execute(
            "UPDATE index_jobs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
            ("failed" if error else "done", error, now(), job_id),
        )

    def requeue_interrupted(self) -> int:
        """Put jobs left 'running' by a stopped or crashed indexer back in the
        queue. They start over; files already indexed are skipped quickly."""
        cur = self._conn.execute(
            """
            UPDATE index_jobs
            SET status = 'queued', processed_files = 0, indexed_files = 0,
                skipped_files = 0, failed_files = 0, started_at = NULL
            WHERE status = 'running'
            """
        )
        return cur.rowcount
