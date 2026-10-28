CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS images_ocr_text_trgm_idx
ON images USING gin (ocr_text gin_trgm_ops);
