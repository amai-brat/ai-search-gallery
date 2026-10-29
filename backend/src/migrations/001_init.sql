CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS images (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    sha256sum TEXT UNIQUE NOT NULL,
    filepath TEXT UNIQUE NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ocr_text TEXT, 
    embedding VECTOR(768)
);

CREATE INDEX IF NOT EXISTS hnsw_index ON images 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);