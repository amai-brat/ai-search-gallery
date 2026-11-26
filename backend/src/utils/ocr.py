import logging
import threading
from pathlib import Path
from typing import Any

from utils.config import MODELS_DIR, OCR_MAX_SIDE, OCR_THREADS

logger = logging.getLogger(__name__)

_ocr: Any = None
_lock = threading.Lock()


def _params() -> dict[str, Any]:
    """RapidOCR settings that reproduce the former PaddleOCR pipeline.

    Same models (PP-OCRv5 mobile detector, eslav mobile recognizer), converted to
    ONNX by RapidOCR, and the same detector thresholds PaddleOCR uses for them.
    """
    from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion

    models_dir = MODELS_DIR / "rapidocr"
    models_dir.mkdir(parents=True, exist_ok=True)
    return {
        "Global.model_root_dir": str(models_dir),
        # "warning" would log every image without text ("detection result is empty").
        "Global.log_level": "error",
        # Text line orientation classifier: off, as it was with PaddleOCR.
        "Global.use_cls": False,
        # Downscale large photos before detection: phone photos (4000 px)
        # otherwise make the detector many times slower for the same text.
        "Global.max_side_len": OCR_MAX_SIDE or 100_000,
        # Keep every recognized line, like PaddleOCR (text_rec_score_thresh=0).
        "Global.text_score": 0.0,
        "Det.engine_type": EngineType.ONNXRUNTIME,
        "Det.lang_type": LangDet.CH,  # the multilingual PP-OCRv5 detector
        "Det.model_type": ModelType.MOBILE,
        "Det.ocr_version": OCRVersion.PPOCRV5,
        # PaddleOCR defaults for PP-OCRv5_mobile_det: do not upscale images whose
        # short side is above 64 px.
        "Det.limit_side_len": 64,
        "Det.limit_type": "min",
        "Det.thresh": 0.3,
        "Det.box_thresh": 0.6,
        "Det.unclip_ratio": 1.5,
        # PaddleOCR does not dilate the text mask; RapidOCR does by default, which
        # merges neighbouring words (bench/ocr: worse on Russian text).
        "Det.use_dilation": False,
        "Rec.engine_type": EngineType.ONNXRUNTIME,
        "Rec.lang_type": LangRec.ESLAV,
        "Rec.model_type": ModelType.MOBILE,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "EngineConfig.onnxruntime.intra_op_num_threads": OCR_THREADS or -1,
    }


def load_ocr() -> Any:
    """Lazily create the OCR engine (downloads the models on first use)."""
    global _ocr
    with _lock:
        if _ocr is None:
            from rapidocr import RapidOCR

            params = _params()
            logger.info(
                "Loading RapidOCR (PP-OCRv5 mobile det + eslav rec, max side %s px, "
                "%s threads)",
                OCR_MAX_SIDE,
                OCR_THREADS or "auto",
            )
            _ocr = RapidOCR(params=params)
    return _ocr


def _extract_texts(result: Any) -> list[str]:
    texts: list[str] = []
    for text in getattr(result, "txts", None) or ():
        text = str(text).strip()
        if text:
            texts.append(text)
    return texts


def get_image_text(image: str | Path | Any) -> str:
    """Run OCR on an image (path, PIL image or RGB array); one line per text box."""
    ocr = load_ocr()
    if isinstance(image, Path):
        image = str(image)
    result = ocr(image, use_cls=False)
    return "\n".join(_extract_texts(result))
