from repositories.image_repository import ImageRepository
from utils.database import get_db_connection


def get_repository():
    with get_db_connection() as conn:
        yield ImageRepository(conn)
