"""SQLite database shared by the API process and the indexer process.

WAL mode lets readers work while the indexer writes; writes are short single
statements, and the busy timeout covers the rare moment when both write.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from utils.config import DATABASE_PATH


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit: every statement is its own transaction unless BEGIN is used.
    conn = sqlite3.connect(
        DATABASE_PATH, timeout=30, isolation_level=None, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db_connection() -> Iterator[sqlite3.Connection]:
    """A short-lived connection (opening one is cheap in SQLite)."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def now() -> str:
    """Current UTC time as stored in the database (ISO 8601)."""
    return datetime.now(UTC).isoformat()
