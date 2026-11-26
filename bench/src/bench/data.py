"""Crossmodal-3600 (XM3600): 3600 images, human captions in 36 languages.

https://google.github.io/crossmodal-3600/

The loader returns captions *and* their ground-truth image index from one loop,
so the two lists can never get out of sync (the first version of the benchmark
built them in different orders, which gave chance-level recall for every model).
"""

from __future__ import annotations

import json
import os
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from tqdm.auto import tqdm

IMAGES_URL = "https://open-images-dataset.s3.amazonaws.com/crossmodal-3600/images.tgz"
CAPTIONS_URL = "https://google.github.io/crossmodal-3600/web-data/captions.zip"

DEFAULT_CACHE = Path(
    os.getenv("XM3600_CACHE") or Path.home() / "models" / "datasets" / "xm3600"
)

META_KEYS = {"image/key", "image/locale"}


@dataclass
class RetrievalSet:
    """Text -> image retrieval task.

    ``texts[i]`` is a caption in language ``text_lang[i]``; the image it
    describes is ``image_paths[text_img[i]]``.
    """

    image_paths: list[Path]
    texts: list[str]
    text_lang: np.ndarray  # (T,) str
    text_img: np.ndarray  # (T,) int
    langs: list[str]

    def __post_init__(self) -> None:
        assert len(self.texts) == len(self.text_lang) == len(self.text_img)
        assert self.text_img.max() < len(self.image_paths)


def _download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    print(f"Downloading {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        with tqdm(total=total or None, unit="B", unit_scale=True, desc=dest.name) as bar:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
                bar.update(len(chunk))
    tmp.replace(dest)


def _find_dir_with(root: Path, suffix: str) -> Path | None:
    for dirpath, _, filenames in os.walk(root):
        if any(f.endswith(suffix) for f in filenames):
            return Path(dirpath)
    return None


def ensure_images(cache: Path = DEFAULT_CACHE) -> Path:
    images_dir = cache / "images"
    found = _find_dir_with(images_dir, ".jpg") if images_dir.is_dir() else None
    if found:
        return found
    tgz = cache / "images.tgz"
    _download(IMAGES_URL, tgz)
    print("Extracting images ...")
    images_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz, "r:gz") as tar:
        tar.extractall(images_dir, filter="data")
    found = _find_dir_with(images_dir, ".jpg")
    if found is None:
        raise RuntimeError(f"No .jpg files found under {images_dir}")
    return found


def ensure_captions(cache: Path = DEFAULT_CACHE) -> Path:
    target = cache / "captions.jsonl"
    if target.exists() and target.stat().st_size > 0:
        return target
    zip_path = cache / "captions.zip"
    _download(CAPTIONS_URL, zip_path)
    print("Extracting captions ...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(cache)
    if target.exists():
        return target
    for dirpath, _, filenames in os.walk(cache):
        if "captions.jsonl" in filenames:
            os.replace(Path(dirpath) / "captions.jsonl", target)
            return target
    raise RuntimeError("captions.jsonl not found in the archive")


def load_retrieval_set(
    n_images: int | None = 1000,
    langs: list[str] | None = None,
    seed: int = 0,
    cache: Path = DEFAULT_CACHE,
) -> RetrievalSet:
    """Random (seeded) subset of ``n_images`` images with captions in ``langs``.

    A random subset is used rather than the first rows because the file may be
    grouped by locale.
    """
    langs = langs or ["en", "ru"]
    images_dir = ensure_images(cache)
    captions = ensure_captions(cache)

    with open(captions, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    if n_images is not None and n_images < len(rows):
        idx = np.sort(np.random.default_rng(seed).choice(len(rows), n_images, replace=False))
        rows = [rows[i] for i in idx]

    missing = [lang for lang in langs if lang not in rows[0]]
    if missing:
        raise ValueError(f"Languages not in the dataset: {missing}")

    image_paths: list[Path] = []
    texts: list[str] = []
    text_lang: list[str] = []
    text_img: list[int] = []
    for img_idx, row in enumerate(rows):
        image_paths.append(images_dir / f"{row['image/key']}.jpg")
        for lang in langs:
            for caption in row.get(lang, {}).get("caption", []):
                texts.append(caption)
                text_lang.append(lang)
                text_img.append(img_idx)

    return RetrievalSet(
        image_paths=image_paths,
        texts=texts,
        text_lang=np.array(text_lang),
        text_img=np.array(text_img),
        langs=langs,
    )
