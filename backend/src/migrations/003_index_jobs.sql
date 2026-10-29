CREATE TABLE IF NOT EXISTS index_jobs (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    kind TEXT NOT NULL DEFAULT 'folder',
    directory_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    total_files INTEGER,
    processed_files INTEGER NOT NULL DEFAULT 0,
    indexed_files INTEGER NOT NULL DEFAULT 0,
    skipped_files INTEGER NOT NULL DEFAULT 0,
    failed_files INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS index_jobs_created_at_idx ON index_jobs (created_at DESC);
