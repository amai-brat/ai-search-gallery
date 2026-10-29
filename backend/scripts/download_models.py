"""Download and warm up the CLIP and PaddleOCR models configured in ``.env``.

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
    # HF cache snapshots are symlinks to blobs: skip them to avoid double counting.
    return (
        sum(
            f.stat().st_size
            for f in path.rglob("*")
            if f.is_file() and not f.is_symlink()
        )
        / 1e6
    )


def main() -> None:
    from huggingface_hub.constants import HF_HUB_CACHE
    from utils import config

    hf_cache = Path(HF_HUB_CACHE)
    paddle_cache = Path(
        os.getenv("PADDLE_PDX_CACHE_HOME", Path.home() / ".paddlex")
    )

    print(f"CLIP model:  {config.CLIP_MODEL_NAME}")
    print(f"OCR models:  det={config.PADDLEOCR_DET_MODEL or 'auto'}, "
          f"rec={config.PADDLEOCR_REC_MODEL or 'auto'}")

    from utils.ml_core import get_text_embedding, load_model

    print("\n[1/2] Downloading CLIP (this is ~1.5 GB, only the first time) ...")
    load_model()
    dim = len(get_text_embedding("test"))
    print(f"      OK, embedding size = {dim}")

    from utils.ocr import load_ocr

    print("\n[2/2] Downloading PaddleOCR models ...")
    load_ocr()
    print("      OK")

    print("\nModels are stored here (delete these folders to remove them):")
    print(f"  CLIP      {hf_cache}  ({dir_size_mb(hf_cache):,.0f} MB)")
    print(f"  PaddleOCR {paddle_cache}  ({dir_size_mb(paddle_cache):,.0f} MB)")


if __name__ == "__main__":
    main()
