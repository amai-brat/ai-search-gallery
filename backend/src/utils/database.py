import atexit
from contextlib import contextmanager

from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool
from utils.config import DATABASE_URL

db_pool = ConnectionPool(DATABASE_URL, open=False)
atexit.register(db_pool.close)


def open_pool():
    """Call this once at app startup (e.g. in main / FastAPI lifespan)."""
    db_pool.open()


@contextmanager
def get_db_connection():
    """Yield a pooled connection with pgvector registered."""
    with db_pool.connection() as conn:
        register_vector(conn)
        yield conn
