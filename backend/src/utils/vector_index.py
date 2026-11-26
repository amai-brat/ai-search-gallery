"""In-memory copy of the CLIP vectors for exact nearest-neighbour search.

The vectors are stored in SQLite (images.embedding); this index keeps them in
one float32 matrix so a query is a single matrix-vector product: about 1 ms per
10 000 images, 30 MB of memory per 10 000 images. (float16 would halve the
memory, but numpy has no fast float16 product: ~25x slower.)

Before each search the index loads the rows written since it last looked, so
images indexed by the indexer process become searchable right away.
"""

import threading

import numpy as np
from repositories.image_repository import ImageRepository, decode_vector
from utils.database import get_db_connection


class VectorIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ids = np.empty(0, dtype=np.int64)
        self._matrix = np.empty((0, 0), dtype=np.float32)
        self._row_of: dict[int, int] = {}
        self._version = 0

    def refresh(self) -> None:
        with get_db_connection() as conn:
            repo = ImageRepository(conn)
            if repo.max_version() <= self._version:
                return
            with self._lock:
                rows = repo.vectors_since(self._version)
                if rows:
                    self._apply(rows)

    def _apply(self, rows) -> None:
        new_ids, new_vectors = [], []
        for row in rows:
            vector = decode_vector(row["embedding"])
            pos = self._row_of.get(row["id"])
            if pos is not None:  # vector of a known image was rewritten
                self._matrix[pos] = vector
            else:
                new_ids.append(row["id"])
                new_vectors.append(vector)
            self._version = max(self._version, row["version"])
        if new_ids:
            start = len(self._ids)
            block = np.stack(new_vectors).astype(np.float32)
            self._matrix = (
                np.concatenate([self._matrix, block]) if start else block.copy()
            )
            self._ids = np.concatenate([self._ids, np.asarray(new_ids, dtype=np.int64)])
            self._row_of.update({i: start + k for k, i in enumerate(new_ids)})

    def nearest(self, vector: list[float], limit: int) -> list[tuple[int, float]]:
        """``limit`` nearest images as (id, cosine distance), closest first."""
        self.refresh()
        with self._lock:
            if not len(self._ids):
                return []
            query = np.asarray(vector, dtype=np.float32)
            # Vectors are L2-normalized, so cosine distance = 1 - dot product
            # (the same value pgvector's <=> returned before).
            distances = 1.0 - self._matrix @ query
            k = min(limit, len(distances))
            top = np.argpartition(distances, k - 1)[:k]
            top = top[np.argsort(distances[top])]
            return [(int(self._ids[i]), float(distances[i])) for i in top]

    def __len__(self) -> int:
        return len(self._ids)


vector_index = VectorIndex()
