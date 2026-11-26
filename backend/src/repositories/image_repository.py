import sqlite3
from collections.abc import Iterable, Sequence

import numpy as np
from models.image import Image, ImageCreate
from utils.search_query import compile_ocr_filter
from utils.text_norm import normalize, stems_column

_COLUMNS = "id, sha256sum, filepath, added_at, ocr_text"


def encode_vector(vector: Sequence[float]) -> bytes:
    return np.asarray(vector, dtype="<f4").tobytes()


def decode_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="<f4")


def _image(row: sqlite3.Row) -> Image:
    data = dict(row)
    blob = data.pop("embedding", None)
    if blob is not None:
        data["embedding"] = decode_vector(blob).tolist()
    return Image.model_validate(data)


class ImageRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get_by_sha256(self, sha256sum: str) -> Image | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS}, embedding FROM images WHERE sha256sum = ?",
            (sha256sum,),
        ).fetchone()
        return _image(row) if row else None

    def get(self, image_id: int) -> Image | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM images WHERE id = ?", (image_id,)
        ).fetchone()
        return _image(row) if row else None

    def get_many(self, ids: Iterable[int]) -> dict[int, Image]:
        ids = list(ids)
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM images WHERE id IN ({marks})", ids
        ).fetchall()
        return {row["id"]: _image(row) for row in rows}

    def get_all(self, offset: int, limit: int = 20) -> list[Image]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM images ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_image(r) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT count(*) FROM images").fetchone()[0]

    def upsert(self, data: ImageCreate) -> int:
        """Insert or update an image by checksum; returns its id.

        Missing values (None) never overwrite values already stored, so a later
        run can fill in what an earlier one could not compute.
        """
        ocr = data.ocr_text
        row = self._conn.execute(
            """
            INSERT INTO images (sha256sum, filepath, added_at, ocr_text, ocr_norm,
                                ocr_stems, embedding, version)
            VALUES (?, ?, ?, ?, ?, ?, ?,
                    (SELECT coalesce(max(version), 0) + 1 FROM images))
            ON CONFLICT (sha256sum) DO UPDATE
            SET filepath = excluded.filepath,
                ocr_text = coalesce(excluded.ocr_text, images.ocr_text),
                ocr_norm = coalesce(excluded.ocr_norm, images.ocr_norm),
                ocr_stems = coalesce(excluded.ocr_stems, images.ocr_stems),
                embedding = coalesce(excluded.embedding, images.embedding),
                version = excluded.version
            RETURNING id
            """,
            (
                data.sha256sum,
                data.filepath,
                data.added_at.isoformat(),
                ocr,
                normalize(ocr) if ocr is not None else None,
                stems_column(ocr) if ocr is not None else None,
                encode_vector(data.embedding) if data.embedding is not None else None,
            ),
        ).fetchone()
        return row[0]

    def vectors_since(self, version: int) -> list[sqlite3.Row]:
        """Rows with a vector written after ``version`` (for the vector index)."""
        return self._conn.execute(
            """
            SELECT id, embedding, version FROM images
            WHERE version > ? AND embedding IS NOT NULL
            ORDER BY version
            """,
            (version,),
        ).fetchall()

    def max_version(self) -> int:
        return self._conn.execute(
            "SELECT coalesce(max(version), 0) FROM images"
        ).fetchone()[0]

    def search_ocr(self, query: str, limit: int = 10) -> list[Image]:
        """Return images whose OCR text matches a Kibana-like query."""
        condition, params = compile_ocr_filter(query)
        rows = self._conn.execute(
            f"""
            SELECT {_COLUMNS} FROM images
            WHERE ocr_text IS NOT NULL AND ({condition})
            ORDER BY id
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [_image(r) for r in rows]
