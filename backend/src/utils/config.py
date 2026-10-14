import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5433/gallery"
)

CELERY_BROKER = os.getenv("CELERY_BROKER", "redis://localhost:6379")

CLIP_MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "ViT-L-16-SigLIP2-256")
