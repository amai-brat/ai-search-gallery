import os
from pathlib import Path

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5434/gallery"
)

CELERY_BROKER = os.getenv("CELERY_BROKER", "redis://localhost:6380")

# Must carry a "hf-hub:" (or "local-dir:") prefix: with a bare model name
# open_clip would build the architecture with random, untrained weights.
# The vector size of the model must match images.embedding in the migrations
# (768 for ViT-B-16-SigLIP2).
CLIP_MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "hf-hub:timm/ViT-B-16-SigLIP2")

# Light PP-OCRv5 mobile models. The eslav recognizer reads Russian, Belarusian,
# Ukrainian and English. Set both to empty strings to let PaddleOCR choose the
# models from PADDLEOCR_LANG instead (it then picks the heavier server detector).
PADDLEOCR_DET_MODEL = os.getenv("PADDLEOCR_DET_MODEL", "PP-OCRv5_mobile_det")
PADDLEOCR_REC_MODEL = os.getenv("PADDLEOCR_REC_MODEL", "eslav_PP-OCRv5_mobile_rec")

# Used only when PADDLEOCR_DET_MODEL and PADDLEOCR_REC_MODEL are both empty.
PADDLEOCR_LANG = os.getenv("PADDLEOCR_LANG", "ru")

# Examples: "cpu", "gpu", "gpu:0". Leave empty to let PaddleOCR choose
# (GPU 0 when available, CPU otherwise).
PADDLEOCR_DEVICE = os.getenv("PADDLEOCR_DEVICE", "")

# PaddlePaddle 3.x can crash on CPU with oneDNN/MKLDNN enabled, so it is off by
# default. Set PADDLEOCR_ENABLE_MKLDNN=true to opt in.
PADDLEOCR_ENABLE_MKLDNN = os.getenv("PADDLEOCR_ENABLE_MKLDNN", "").lower() in (
    "1",
    "true",
    "yes",
)

# Uploaded images and cached thumbnails live here.
STORAGE_DIR = Path(
    os.getenv("STORAGE_DIR") or Path(__file__).resolve().parents[2] / "storage"
)

# Origins allowed to call the API from a browser (the Vite dev server by default).
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:5180,http://127.0.0.1:5180"
    ).split(",")
    if o.strip()
]

# Semantic search relevance. SigLIP cosine distances are compressed (relevant and
# irrelevant hits differ by hundredths) and their scale shifts from query to
# query, so a fixed cut-off does not work. Instead a hit is kept when its
# distance is within this window of the best hit for the same query.
# Tuned on the sample set; increase the windows for a more lenient search.
SEMANTIC_WINDOW_STRICT = float(os.getenv("SEMANTIC_WINDOW_STRICT", "0.010"))
SEMANTIC_WINDOW_BALANCED = float(os.getenv("SEMANTIC_WINDOW_BALANCED", "0.018"))
SEMANTIC_WINDOW_WIDE = float(os.getenv("SEMANTIC_WINDOW_WIDE", "0.035"))
