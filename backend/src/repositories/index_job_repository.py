from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel

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


class IndexJobRepository:
    def __init__(self, conn: Connection):
        self._conn = conn

    def create(self, directory_path: str, kind: str = "folder") -> IndexJob:
        sql = f"""
            INSERT INTO index_jobs (directory_path, kind)
            VALUES (%s, %s)
            RETURNING {_COLUMNS}
        """
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (directory_path, kind))  # type: ignore
            job = IndexJob.model_validate(cur.fetchone())
        # Commit right away: the worker must see the row as soon as the task is queued.
        self._conn.commit()
        return job

    def list(self, limit: int = 50) -> list[IndexJob]:
        sql = f"""
            SELECT {_COLUMNS} FROM index_jobs
            ORDER BY created_at DESC, id DESC
            LIMIT %s
        """
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (limit,))  # type: ignore
            return [IndexJob.model_validate(r) for r in cur.fetchall()]

    def mark_running(self, job_id: int, total_files: int) -> None:
        self._conn.execute(
            """
            UPDATE index_jobs
            SET status = 'running', total_files = %s, started_at = now()
            WHERE id = %s
            """,
            (total_files, job_id),
        )

    def add_progress(
        self, job_id: int, *, indexed: int = 0, skipped: int = 0, failed: int = 0
    ) -> None:
        self._conn.execute(
            """
            UPDATE index_jobs
            SET processed_files = processed_files + %s + %s + %s,
                indexed_files = indexed_files + %s,
                skipped_files = skipped_files + %s,
                failed_files = failed_files + %s
            WHERE id = %s
            """,
            (indexed, skipped, failed, indexed, skipped, failed, job_id),
        )

    def finish(self, job_id: int, error: str | None = None) -> None:
        self._conn.execute(
            """
            UPDATE index_jobs
            SET status = %s, error = %s, finished_at = now()
            WHERE id = %s
            """,
            ("failed" if error else "done", error, job_id),
        )

    def fail_stale(self, error: str) -> None:
        """Mark jobs left in 'running' by a crashed worker as failed."""
        self._conn.execute(
            """
            UPDATE index_jobs
            SET status = 'failed', error = %s, finished_at = now()
            WHERE status = 'running'
            """,
            (error,),
        )
