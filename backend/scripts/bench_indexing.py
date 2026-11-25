"""End-to-end indexing benchmark: the same per-file work the worker does.

Run from ``backend``::

    uv run python scripts/bench_indexing.py make-dataset
    uv run python scripts/bench_indexing.py run --label baseline
    uv run python scripts/bench_indexing.py compare baseline onnx-ocr

``make-dataset`` builds ``bench/e2e/data`` (not in git) from three groups:

* ``small``: ``test-images`` as is (photos up to 1280 px and text boards);
* ``synthetic``: the OCR benchmark set ``bench/ocr/data/images`` (1024x768);
* ``phone``: the photos from ``test-images`` upscaled to 4032 px on the long side.
  The extra pixels are fake, but decoding and text detection cost depends on the
  size; OCR quality is measured separately in ``bench/ocr``.

``run`` calls ``get_image_embedding`` / ``get_image_text`` / ``get_text_embedding``
from ``src/utils`` (whatever implementation is current) and writes timings,
recognized text and vectors to ``bench/e2e/results/<label>.json`` / ``.npz``, so
later implementations can be compared with the baseline for both speed and output.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
E2E = REPO / "bench" / "e2e"
DATA = E2E / "data"
RESULTS = E2E / "results"
GROUPS = ("small", "synthetic", "phone")
PHONE_SIDE = 4032

QUERIES = [
    "кошка на диване", "собака на пляже", "дорожный знак", "вывеска магазина",
    "красная машина", "горное озеро", "пицца", "велосипед", "чашка кофе", "подсолнух",
    "a cat on a sofa", "a dog on the beach", "road sign", "shop sign", "red car",
    "mountain lake", "pizza", "bicycle", "cup of coffee", "sunflower",
]

sys.path.insert(0, str(BACKEND / "src"))


def load_env() -> None:
    env_file = BACKEND / ".env"
    if not env_file.is_file():
        return
    try:
        import dotenv
    except ImportError:
        return
    dotenv.load_dotenv(env_file)


def peak_rss_mb() -> float:
    try:
        import psutil

        info = psutil.Process().memory_info()
        return getattr(info, "peak_wset", info.rss) / 2**20
    except ImportError:
        pass
    if sys.platform != "win32":
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                         "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                         "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")
        ]

    counters = Counters(cb=ctypes.sizeof(Counters))
    get_info = ctypes.WinDLL("psapi").GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    process = ctypes.windll.kernel32.GetCurrentProcess()
    if not get_info(process, ctypes.byref(counters), counters.cb):
        return float("nan")
    return counters.PeakWorkingSetSize / 2**20


# --------------------------------------------------------------------- dataset


def make_dataset(force: bool) -> None:
    from PIL import Image

    if DATA.exists():
        if not force:
            raise SystemExit(f"{DATA} already exists, pass --force to rebuild it")
        shutil.rmtree(DATA)

    test_images = REPO / "test-images"
    synthetic = REPO / "bench" / "ocr" / "data" / "images"
    for src, name in ((test_images, "test-images (backend/scripts/fetch_test_images.py)"),
                      (synthetic, "bench/ocr/data/images (bench/ocr/make_dataset.py)")):
        if not src.is_dir():
            raise SystemExit(f"Missing {src}: build {name} first")

    counts = dict.fromkeys(GROUPS, 0)
    for group in GROUPS:
        (DATA / group).mkdir(parents=True)

    for f in sorted(test_images.iterdir()):
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            shutil.copy2(f, DATA / "small" / f.name)
            counts["small"] += 1
        if f.suffix.lower() in (".jpg", ".jpeg"):
            with Image.open(f) as img:
                img = img.convert("RGB")
                scale = PHONE_SIDE / max(img.size)
                size = (round(img.width * scale), round(img.height * scale))
                img.resize(size, Image.Resampling.LANCZOS).save(
                    DATA / "phone" / f.name, "JPEG", quality=90
                )
            counts["phone"] += 1

    for f in sorted(synthetic.iterdir()):
        if f.is_file():
            shutil.copy2(f, DATA / "synthetic" / f.name)
            counts["synthetic"] += 1

    print(f"Dataset in {DATA}: " + ", ".join(f"{g} {n}" for g, n in counts.items()))


def list_files(groups: list[str], limit: int | None) -> list[tuple[str, Path]]:
    if not DATA.is_dir():
        raise SystemExit(f"No dataset in {DATA}: run make-dataset first")
    files: list[tuple[str, Path]] = []
    for group in groups:
        group_files = sorted((DATA / group).iterdir())
        files += [(group, f) for f in group_files[:limit]]
    return files


# ------------------------------------------------------------------------- run


def run(label: str, groups: list[str], limit: int | None, no_ocr: bool) -> None:
    import numpy as np
    from PIL import Image

    load_env()
    from utils.checksums import sha256sum
    from utils.ml_core import get_image_embedding, get_text_embedding
    from utils.ocr import get_image_text

    files = list_files(groups, limit)
    print(f"[{label}] {len(files)} files, groups: {', '.join(groups)}", flush=True)

    # The first call loads the models; time it separately on a small image.
    warm = next((f for g, f in files if g == "small"), files[0][1])
    t = time.perf_counter()
    get_image_embedding(str(warm))
    clip_load_s = time.perf_counter() - t
    t = time.perf_counter()
    get_text_embedding("warm up")
    text_load_s = time.perf_counter() - t
    ocr_load_s = None
    if not no_ocr:
        t = time.perf_counter()
        get_image_text(str(warm))
        ocr_load_s = time.perf_counter() - t
    print(f"warm-up: clip {clip_load_s:.1f} s, text {text_load_s:.1f} s, "
          f"ocr {ocr_load_s if ocr_load_s is None else round(ocr_load_s, 1)} s", flush=True)

    records: list[dict] = []
    image_vectors: list[list[float]] = []
    wall = time.perf_counter()
    for i, (group, path) in enumerate(files, 1):
        with Image.open(path) as img:
            size = img.size
        t0 = time.perf_counter()
        sha256sum(str(path))
        t1 = time.perf_counter()
        vector = get_image_embedding(str(path))
        t2 = time.perf_counter()
        text = None if no_ocr else get_image_text(str(path))
        t3 = time.perf_counter()
        records.append({
            "file": f"{group}/{path.name}",
            "group": group,
            "width": size[0],
            "height": size[1],
            "hash_ms": (t1 - t0) * 1000,
            "clip_ms": (t2 - t1) * 1000,
            "ocr_ms": None if no_ocr else (t3 - t2) * 1000,
            "total_ms": (t3 - t0) * 1000,
            "text": text,
        })
        image_vectors.append(vector)
        if i % 20 == 0 or i == len(files):
            print(f"  {i}/{len(files)}  last: clip {records[-1]['clip_ms']:.0f} ms, "
                  f"ocr {records[-1]['ocr_ms'] or 0:.0f} ms", flush=True)
    wall_s = time.perf_counter() - wall

    query_ms, query_vectors = [], []
    for q in QUERIES:
        t = time.perf_counter()
        query_vectors.append(get_text_embedding(q))
        query_ms.append((time.perf_counter() - t) * 1000)

    result = {
        "label": label,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
        },
        "groups": groups,
        "no_ocr": no_ocr,
        "load_s": {"clip": clip_load_s, "text": text_load_s, "ocr": ocr_load_s},
        "wall_s": wall_s,
        "peak_rss_mb": peak_rss_mb(),
        "query_ms": query_ms,
        "queries": QUERIES,
        "images": records,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{label}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    np.savez_compressed(
        RESULTS / f"{label}.npz",
        files=np.array([r["file"] for r in records]),
        images=np.asarray(image_vectors, dtype=np.float32),
        queries=np.asarray(query_vectors, dtype=np.float32),
    )
    print_summary(result)


# --------------------------------------------------------------------- reports


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else float("nan")


def summarize(result: dict) -> dict[str, dict[str, float]]:
    rows: dict[str, dict[str, float]] = {}
    images = result["images"]
    for group in [*result["groups"], "all"]:
        recs = images if group == "all" else [r for r in images if r["group"] == group]
        if not recs:
            continue
        rows[group] = {
            "n": len(recs),
            "clip_ms": _median([r["clip_ms"] for r in recs]),
            "ocr_ms": _median([r["ocr_ms"] for r in recs if r["ocr_ms"] is not None]),
            "total_ms": _median([r["total_ms"] for r in recs]),
            "sum_s": sum(r["total_ms"] for r in recs) / 1000,
        }
    return rows


def print_summary(result: dict) -> None:
    rows = summarize(result)
    print(f"\n[{result['label']}] medians per image, ms")
    print(f"{'group':<10} {'n':>4} {'clip':>8} {'ocr':>8} {'total':>8} {'sum, s':>8}")
    for group, r in rows.items():
        print(f"{group:<10} {r['n']:>4} {r['clip_ms']:>8.0f} {r['ocr_ms']:>8.0f} "
              f"{r['total_ms']:>8.0f} {r['sum_s']:>8.1f}")
    n = len(result["images"])
    print(f"wall {result['wall_s']:.1f} s for {n} images "
          f"({n / result['wall_s'] * 60:.0f} images/min), "
          f"query median {_median(result['query_ms']):.0f} ms, "
          f"peak RSS {result['peak_rss_mb']:.0f} MiB")
    load = result["load_s"]
    print("warm-up (load + first call): " + ", ".join(
        f"{k} {v:.1f} s" for k, v in load.items() if v is not None))


def _words(text: str | None) -> set[str]:
    if not text:
        return set()
    return {w for w in text.lower().replace("ё", "е").split() if len(w) > 1}


def compare(base_label: str, new_label: str) -> None:
    import numpy as np

    base = json.loads((RESULTS / f"{base_label}.json").read_text(encoding="utf-8"))
    new = json.loads((RESULTS / f"{new_label}.json").read_text(encoding="utf-8"))
    base_rows, new_rows = summarize(base), summarize(new)

    print(f"{new_label} vs {base_label}: speed-up of median per-image time")
    print(f"{'group':<10} {'clip':>8} {'ocr':>8} {'total':>8}")
    for group in new_rows:
        if group not in base_rows:
            continue
        b, n = base_rows[group], new_rows[group]
        print(f"{group:<10} " + " ".join(
            f"{b[k] / n[k]:>7.2f}x" if n[k] == n[k] and n[k] > 0 else f"{'-':>8}"
            for k in ("clip_ms", "ocr_ms", "total_ms")))
    print(f"wall: {base['wall_s']:.1f} s -> {new['wall_s']:.1f} s "
          f"({base['wall_s'] / new['wall_s']:.2f}x), peak RSS "
          f"{base['peak_rss_mb']:.0f} -> {new['peak_rss_mb']:.0f} MiB")

    bz, nz = np.load(RESULTS / f"{base_label}.npz"), np.load(RESULTS / f"{new_label}.npz")
    index = {f: i for i, f in enumerate(bz["files"])}
    pairs = [(index[f], j) for j, f in enumerate(nz["files"]) if f in index]
    if pairs and bz["images"].shape[1] == nz["images"].shape[1]:
        bi = bz["images"][[i for i, _ in pairs]]
        ni = nz["images"][[j for _, j in pairs]]
        cos = (bi * ni).sum(1) / (np.linalg.norm(bi, axis=1) * np.linalg.norm(ni, axis=1))
        print(f"image vectors: cosine min {cos.min():.5f}, median {np.median(cos):.5f}")
        if bz["queries"].shape == nz["queries"].shape:
            bq, nq = bz["queries"], nz["queries"]
            qcos = (bq * nq).sum(1) / (np.linalg.norm(bq, axis=1) * np.linalg.norm(nq, axis=1))
            print(f"query vectors: cosine min {qcos.min():.5f}, median {np.median(qcos):.5f}")
    else:
        print("image vectors: different files or dimensions, not compared")

    base_text = {r["file"]: r["text"] for r in base["images"] if r["text"] is not None}
    recalls = []
    for r in new["images"]:
        ref = _words(base_text.get(r["file"]))
        if ref and r["text"] is not None:
            recalls.append(len(ref & _words(r["text"])) / len(ref))
    if recalls:
        print(f"OCR words of {base_label} also found by {new_label}: "
              f"mean {statistics.mean(recalls):.3f} over {len(recalls)} images with text")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make-dataset", help="build bench/e2e/data")
    m.add_argument("--force", action="store_true", help="rebuild an existing dataset")
    r = sub.add_parser("run", help="time the current implementation")
    r.add_argument("--label", required=True, help="results name, e.g. baseline")
    r.add_argument("--groups", nargs="+", choices=GROUPS, default=list(GROUPS))
    r.add_argument("--limit", type=int, help="at most N files per group")
    r.add_argument("--no-ocr", action="store_true", help="CLIP only")
    c = sub.add_parser("compare", help="compare two runs")
    c.add_argument("base")
    c.add_argument("new")
    a = p.parse_args()

    if a.cmd == "make-dataset":
        make_dataset(a.force)
    elif a.cmd == "run":
        run(a.label, a.groups, a.limit, a.no_ocr)
    else:
        compare(a.base, a.new)


if __name__ == "__main__":
    main()
