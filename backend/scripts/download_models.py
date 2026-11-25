"""Download and warm up the CLIP and OCR models configured in ``.env``.

Run from ``backend``::

    uv run --env-file .env python scripts/download_models.py

It uses the same loading code as the app, so a successful run means the
service will not need to download anything on first use.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def main() -> None:
    from utils import config

    print(f"CLIP model:  {config.CLIP_MODEL_REPO} (ONNX)")
    print("OCR models:  PP-OCRv5 mobile det + eslav mobile rec (RapidOCR, ONNX)")

    from utils.ml_core import get_text_embedding, load_model, model_dir

    print("\n[1/2] Downloading CLIP (~1.5 GB, only the first time) ...")
    load_model()
    dim = len(get_text_embedding("test"))
    print(f"      OK, embedding size = {dim}")

    from utils.ocr import load_ocr

    print("\n[2/2] Downloading OCR models (~13 MB) ...")
    load_ocr()
    print("      OK")

    ocr_dir = config.MODELS_DIR / "rapidocr"
    print("\nModels are stored here (delete these folders to remove them):")
    print(f"  CLIP {model_dir()}  ({dir_size_mb(model_dir()):,.0f} MB)")
    print(f"  OCR  {ocr_dir}  ({dir_size_mb(ocr_dir):,.0f} MB)")


if __name__ == "__main__":
    main()
