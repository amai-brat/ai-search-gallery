import os
from pathlib import Path

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5434/gallery"
)

CELERY_BROKER = os.getenv("CELERY_BROKER", "redis://localhost:6380")

# Downloaded ONNX models (CLIP and OCR).
MODELS_DIR = Path(
    os.getenv("MODELS_DIR") or Path(__file__).resolve().parents[2] / "models"
)

# OpenCLIP model exported to ONNX (visual and text encoders separately); it is
# downloaded from Hugging Face on first use. CLIP_MODEL_REPO is the repository
# with the export, CLIP_MODEL_NAME the folder under MODELS_DIR/clip. The vector
# size must match images.embedding in the migrations (768 for SigLIP2 B-16 and
# B-32-256); a different model needs a full reindex.
# The old open_clip form "hf-hub:timm/ViT-B-16-SigLIP2" is accepted too.
CLIP_MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "ViT-B-16-SigLIP2").rsplit("/", 1)[-1]
CLIP_MODEL_REPO = os.getenv(
    "CLIP_MODEL_REPO", f"immich-app/{CLIP_MODEL_NAME}__webli"
)

# ONNX Runtime threads per CLIP encoder; 0 lets ONNX Runtime decide.
CLIP_THREADS = int(os.getenv("CLIP_THREADS", "0"))

# OCR runs RapidOCR (ONNX Runtime) with the PP-OCRv5 mobile detector and the
# eslav mobile recognizer (Russian, Belarusian, Ukrainian and English).
# Larger images are downscaled to this many pixels on the long side before text
# detection; 0 disables the downscale.
OCR_MAX_SIDE = int(os.getenv("OCR_MAX_SIDE", "960"))

# ONNX Runtime threads per OCR model; 0 lets ONNX Runtime decide.
OCR_THREADS = int(os.getenv("OCR_THREADS", "0"))

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
