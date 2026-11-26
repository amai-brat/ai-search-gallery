CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256sum TEXT UNIQUE NOT NULL,
    filepath TEXT UNIQUE NOT NULL,
    added_at TEXT NOT NULL,
    -- Recognized text as is (shown to the user) ...
    ocr_text TEXT,
    -- ... lower-cased with ё -> е, for substring search (SQLite's LIKE folds
    -- case of Latin letters only) ...
    ocr_norm TEXT,
    -- ... and word stems (" stem1 stem2 ... "), so other word forms match.
    ocr_stems TEXT,
    -- CLIP vector, float32 little-endian.
    embedding BLOB,
    -- Bumped on every write; the in-memory vector index reloads rows above the
    -- version it has seen.
    version INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS images_version_idx ON images (version);

CREATE TABLE IF NOT EXISTS index_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'folder',
    directory_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    total_files INTEGER,
    processed_files INTEGER NOT NULL DEFAULT 0,
    indexed_files INTEGER NOT NULL DEFAULT 0,
    skipped_files INTEGER NOT NULL DEFAULT 0,
    failed_files INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS index_jobs_status_idx ON index_jobs (status, id);
