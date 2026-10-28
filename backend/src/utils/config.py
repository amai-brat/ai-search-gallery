import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5433/gallery"
)

CELERY_BROKER = os.getenv("CELERY_BROKER", "redis://localhost:6379")

CLIP_MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "ViT-L-16-SigLIP2-256")

PADDLEOCR_LANG = os.getenv("PADDLEOCR_LANG", "en")

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
