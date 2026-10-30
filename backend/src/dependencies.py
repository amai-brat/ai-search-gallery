from repositories.image_repository import ImageRepository
from repositories.index_job_repository import IndexJobRepository
from utils.database import get_db_connection


def get_repository():
    with get_db_connection() as conn:
        yield ImageRepository(conn)


def get_index_job_repository():
    with get_db_connection() as conn:
        yield IndexJobRepository(conn)
