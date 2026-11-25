"""CLIP (SigLIP2) image and text embeddings on ONNX Runtime.

The model is an OpenCLIP export with the visual and text encoders in separate
ONNX files, so the API process (text queries only) and the indexer (images
only) each load just the half they need.
"""

import html
import json
import logging
import string
import threading
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps
from utils.config import CLIP_MODEL_NAME, CLIP_MODEL_REPO, CLIP_THREADS, MODELS_DIR

logger = logging.getLogger(__name__)

_FILES = [
    "config.json",
    "visual/model.onnx",
    "visual/preprocess_cfg.json",
    "textual/model.onnx",
    "textual/tokenizer.json",
]

_lock = threading.Lock()
_visual: Any = None
_textual: Any = None


def model_dir() -> Path:
    return MODELS_DIR / "clip" / CLIP_MODEL_NAME


def download_model() -> Path:
    """Download the export unless it is already there; returns its folder."""
    target = model_dir()
    if all((target / f).is_file() for f in _FILES):
        return target
    from huggingface_hub import snapshot_download

    logger.info("Downloading %s to %s", CLIP_MODEL_REPO, target)
    snapshot_download(CLIP_MODEL_REPO, allow_patterns=_FILES, local_dir=target)
    return target


class _Session:
    """ONNX Runtime session that also accepts batches when the export has a
    fixed batch size of 1 (the Immich exports do): rows then run one by one."""

    def __init__(self, path: Path):
        import onnxruntime as ort

        options = ort.SessionOptions()
        if CLIP_THREADS:
            options.intra_op_num_threads = CLIP_THREADS
        self.session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        inp = self.session.get_inputs()[0]
        self.input = inp.name
        self.type = inp.type
        self.fixed_batch = inp.shape[0] == 1

    def run(self, batch: np.ndarray) -> np.ndarray:
        if self.fixed_batch and len(batch) > 1:
            return np.concatenate([self.run(row[None]) for row in batch])
        return self.session.run(None, {self.input: batch})[0]


class _Visual:
    def __init__(self, folder: Path):
        cfg = json.loads((folder / "visual" / "preprocess_cfg.json").read_text())
        if cfg.get("resize_mode", "squash") != "squash":
            raise ValueError(f"Unsupported resize_mode: {cfg['resize_mode']}")
        self.height, self.width = cfg["size"]
        self.mean = np.array(cfg["mean"], dtype=np.float32).reshape(3, 1, 1)
        self.std = np.array(cfg["std"], dtype=np.float32).reshape(3, 1, 1)
        self.resample = {
            "bicubic": Image.Resampling.BICUBIC,
            "bilinear": Image.Resampling.BILINEAR,
        }[cfg.get("interpolation", "bicubic")]
        self.session = _Session(folder / "visual" / "model.onnx")

    def preprocess(self, image: Image.Image) -> np.ndarray:
        # Same as OpenCLIP's "squash" transform: resize to the model size
        # without keeping the aspect ratio, then normalize.
        image = image.convert("RGB").resize((self.width, self.height), self.resample)
        array = np.asarray(image, dtype=np.float32).transpose(2, 0, 1) / 255.0
        return (array - self.mean) / self.std

    def encode(self, batch: np.ndarray) -> np.ndarray:
        return _normalize(self.session.run(batch))


class _Textual:
    def __init__(self, folder: Path):
        from tokenizers import Tokenizer

        cfg = json.loads((folder / "config.json").read_text())["text_cfg"]
        self.context_length = cfg["context_length"]
        self.clean = cfg.get("tokenizer_kwargs", {}).get("clean", "whitespace")
        self.tokenizer = Tokenizer.from_file(str(folder / "textual" / "tokenizer.json"))
        pad_id = self.tokenizer.token_to_id("<pad>") or 0
        self.tokenizer.enable_padding(length=self.context_length, pad_id=pad_id)
        self.tokenizer.enable_truncation(max_length=self.context_length)
        self.session = _Session(folder / "textual" / "model.onnx")
        self.dtype = np.int64 if "int64" in self.session.type else np.int32

    def tokenize(self, texts: list[str]) -> np.ndarray:
        cleaned = [_clean(t, self.clean) for t in texts]
        ids = [e.ids for e in self.tokenizer.encode_batch(cleaned)]
        return np.asarray(ids, dtype=self.dtype)

    def encode(self, texts: list[str]) -> np.ndarray:
        return _normalize(self.session.run(self.tokenize(texts)))


_PUNCTUATION = str.maketrans("", "", string.punctuation)


def _clean(text: str, mode: str) -> str:
    """OpenCLIP's tokenizer text cleaning (without ftfy, which only repairs
    broken encodings)."""
    text = html.unescape(html.unescape(unicodedata.normalize("NFC", text))).strip()
    if mode == "canonicalize":
        text = text.replace("_", " ").translate(_PUNCTUATION).lower()
    elif mode == "lower":
        text = text.lower()
    return " ".join(text.split())


def _normalize(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32, copy=False)
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def _load_visual() -> _Visual:
    global _visual
    with _lock:
        if _visual is None:
            _visual = _Visual(download_model())
    return _visual


def _load_textual() -> _Textual:
    global _textual
    with _lock:
        if _textual is None:
            _textual = _Textual(download_model())
    return _textual


def load_model() -> None:
    """Load both encoders (used by scripts/download_models.py)."""
    _load_visual()
    _load_textual()


def open_image(path: str | Path, min_side: int = 0) -> Image.Image:
    """Open an image upright (EXIF orientation applied).

    With ``min_side`` a JPEG is decoded at a reduced scale (DCT scaling), never
    below that many pixels on the short side: much faster for large photos.
    """
    with Image.open(path) as image:
        if min_side and image.format == "JPEG":
            w, h = image.size
            scale = max(min_side / min(w, h), 1 / 8)
            if scale < 1:
                image.draft("RGB", (round(w * scale), round(h * scale)))
        # Returns a loaded copy, so the file is closed right away.
        return ImageOps.exif_transpose(image)


def get_image_embeddings(images: list[Image.Image]) -> list[list[float]]:
    """Embed several images in one batch."""
    visual = _load_visual()
    batch = np.stack([visual.preprocess(img) for img in images])
    return visual.encode(batch).tolist()


def get_image_embedding(image: str | Path | Image.Image) -> list[float]:
    if not isinstance(image, Image.Image):
        visual = _load_visual()
        with open_image(image, min_side=2 * max(visual.height, visual.width)) as img:
            return get_image_embeddings([img])[0]
    return get_image_embeddings([image])[0]


@lru_cache(maxsize=256)
def _text_embedding(text: str) -> tuple[float, ...]:
    return tuple(_load_textual().encode([text])[0].tolist())


def get_text_embedding(text_query: str) -> list[float]:
    return list(_text_embedding(text_query))
