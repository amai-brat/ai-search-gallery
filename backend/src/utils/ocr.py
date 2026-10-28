import logging
from pathlib import Path
from typing import Any

from utils.config import (
    PADDLEOCR_DEVICE,
    PADDLEOCR_ENABLE_MKLDNN,
    PADDLEOCR_LANG,
)

logger = logging.getLogger(__name__)

_ocr: Any = None


def load_ocr() -> Any:
    """Lazily create the PaddleOCR pipeline.

    Importing PaddleOCR (and PaddlePaddle itself) is slow, so it is kept out of
    the FastAPI process and only loaded inside Celery workers on first use.
    """
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR

        kwargs: dict[str, Any] = {
            "lang": PADDLEOCR_LANG,
            # These stages are not useful for gallery images and would load
            # additional models on every worker start.
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "enable_mkldnn": PADDLEOCR_ENABLE_MKLDNN,
        }
        if PADDLEOCR_DEVICE:
            kwargs["device"] = PADDLEOCR_DEVICE

        logger.info(
            "Loading PaddleOCR (lang=%s, device=%s)",
            PADDLEOCR_LANG,
            PADDLEOCR_DEVICE or "auto",
        )
        _ocr = PaddleOCR(**kwargs)
    return _ocr


def _extract_texts(result: Any) -> list[str]:
    """Extract recognized lines from PaddleOCR 3.x results.

    The result objects are dict-like and expose ``rec_texts`` (one entry per
    detected text line).
    """
    texts: list[str] = []
    for page in result or []:
        page_texts = page.get("rec_texts") if hasattr(page, "get") else None
        if not page_texts:
            continue
        for text in page_texts:
            text = str(text).strip()
            if text:
                texts.append(text)
    return texts


def get_image_text(image_path: str) -> str:
    """Run OCR on an image and return all recognized text, one line per box."""
    ocr = load_ocr()
    result = ocr.predict(str(Path(image_path)))
    return "\n".join(_extract_texts(result))
