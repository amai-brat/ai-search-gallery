from collections.abc import Sequence

from models.image import Image, ImageCreate, ImageUpdate
from pgvector import Vector
from psycopg import Connection
from psycopg.rows import dict_row


class ImageRepository:
    def __init__(self, conn: Connection):
        self._conn = conn

    def _row_to_dict(self, row: dict | None) -> dict | None:
        """Normalize a DB row dict before Pydantic validation."""
        if row and isinstance(row.get("embedding"), Vector):
            row["embedding"] = row["embedding"].to_list()
        return row

    def insert(self, data: ImageCreate) -> Image:
        sql = """
            INSERT INTO images (sha256sum, filepath, added_at, ocr_text, embedding)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, sha256sum, filepath, added_at, ocr_text, embedding
        """
        params = (
            data.sha256sum,
            data.filepath,
            data.added_at,
            data.ocr_text,
            data.embedding,
        )
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return Image.model_validate(self._row_to_dict(cur.fetchone()))

    def get_by_sha256(self, sha256sum: str) -> Image | None:
        sql = """
            SELECT id, sha256sum, filepath, added_at, ocr_text, embedding
            FROM images WHERE sha256sum = %s
        """
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (sha256sum,))
            row = cur.fetchone()
            return Image.model_validate(row) if row else None

    def get(self, image_id: int) -> Image | None:
        sql = """
            SELECT id, sha256sum, filepath, added_at, ocr_text, embedding
            FROM images WHERE id = %s
        """
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (image_id,))
            row = cur.fetchone()
            return Image.model_validate(self._row_to_dict(row)) if row else None

    def update(self, image_id: int, patch: ImageUpdate) -> Image | None:
        fields = patch.model_dump(exclude_unset=True)
        if not fields:
            return self.get(image_id)

        set_clause = ", ".join(f"{k} = %s" for k in fields)
        sql = f"""
            UPDATE images SET {set_clause}
            WHERE id = %s
            RETURNING id, sha256sum, filepath, added_at, ocr_text, embedding
        """
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (*fields.values(), image_id))  # type: ignore
            row = cur.fetchone()
            return Image.model_validate(self._row_to_dict(row)) if row else None

    def upsert(self, data: ImageCreate) -> Image:
        sql = """
            INSERT INTO images (sha256sum, filepath, added_at, ocr_text, embedding)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (sha256sum) DO UPDATE
            SET filepath = EXCLUDED.filepath,
                ocr_text = COALESCE(EXCLUDED.ocr_text, images.ocr_text),
                embedding = COALESCE(EXCLUDED.embedding, images.embedding)
            RETURNING id, sha256sum, filepath, added_at, ocr_text, embedding
        """
        params = (
            data.sha256sum,
            data.filepath,
            data.added_at,
            data.ocr_text,
            data.embedding,
        )
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return Image.model_validate(self._row_to_dict(cur.fetchone()))

    def nearest(self, embedding: Sequence[float], limit: int = 10) -> list[Image]:
        sql = """
            SELECT id, sha256sum, filepath, added_at, ocr_text
            FROM images
            ORDER BY (embedding <=> %s::vector)
            LIMIT %s
        """
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (embedding, limit))
            return [Image.model_validate(self._row_to_dict(r)) for r in cur.fetchall()]
