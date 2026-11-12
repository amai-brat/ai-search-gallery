"""OCR benchmark: which engine should index the text on gallery photos?

    uv run python ocr_bench.py run --threads 2            # all systems
    uv run python ocr_bench.py run --systems paddle-current --limit 20

Every system reads every image of data/labels.json (see make_dataset.py). Predictions and
per-image timings are cached in results/raw_preds/<system>.json, metrics are computed from
those files by ``metrics()``, so the notebook can be re-run without recognising again.

Metrics (all on text normalised: lower case, e=yo, punctuation removed, single spaces):
* CER   - character error rate: summed edit distance between the reference phrase and the best
          matching group of recognised lines (background text is ignored) / summed reference length
          (synthetic images only, one line of reference text per image);
* word recall - share of reference words found as a substring of the recognised text.
          This is exactly what the app's ocrQuery does, so it is "how often a search by
          a visible word finds the image";
* junk words - recognised words per photo that contains no text.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Callable

from rapidfuzz.distance import Levenshtein

HERE = Path(__file__).resolve().parent
RAW = HERE / "results" / "raw_preds"

# Same settings the backend uses (backend/src/utils/ocr.py): no orientation/unwarping stages.
PADDLE_COMMON = dict(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    enable_mkldnn=False,
    device="cpu",
)

SYSTEMS: dict[str, dict[str, str]] = {
    "paddle-current": {  # what the app runs now
        "det": "PP-OCRv5_mobile_det", "rec": "eslav_PP-OCRv5_mobile_rec",
        "title": "PP-OCRv5 mobile + eslav (сейчас в приложении)",
    },
    "paddle-cyrillic": {
        "det": "PP-OCRv5_mobile_det", "rec": "cyrillic_PP-OCRv5_mobile_rec",
        "title": "PP-OCRv5 mobile + cyrillic",
    },
    "paddle-server-det": {
        "det": "PP-OCRv5_server_det", "rec": "eslav_PP-OCRv5_mobile_rec",
        "title": "PP-OCRv5 server det + eslav",
    },
    "paddle-v3-cyrillic": {
        "det": "PP-OCRv5_mobile_det", "rec": "cyrillic_PP-OCRv3_mobile_rec",
        "title": "PP-OCRv5 det + cyrillic v3 (старый распознаватель)",
    },
    "easyocr": {"title": "EasyOCR (ru+en)"},
}


# --------------------------------------------------------------------------- #
# systems
# --------------------------------------------------------------------------- #
def make_engine(system: str, threads: int) -> Callable[[str], str]:
    cfg = SYSTEMS[system]
    if system == "easyocr":
        import easyocr
        import torch

        torch.set_num_threads(threads)
        reader = easyocr.Reader(["ru", "en"], gpu=False, verbose=False)

        def run_easy(path: str) -> str:
            return "\n".join(reader.readtext(path, detail=0, paragraph=False))

        return run_easy

    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        text_detection_model_name=cfg["det"],
        text_recognition_model_name=cfg["rec"],
        cpu_threads=threads,
        **PADDLE_COMMON,
    )

    def run_paddle(path: str) -> str:
        lines: list[str] = []
        for page in ocr.predict(path) or []:
            for t in (page.get("rec_texts") or []):
                t = str(t).strip()
                if t:
                    lines.append(t)
        return "\n".join(lines)

    return run_paddle


def run_system(system: str, labels: list[dict], threads: int, limit: int | None, force: bool) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    target = RAW / f"{system}.json"
    if target.exists() and not force:
        print(f"[{system}] cached")
        return
    items = labels[:limit] if limit else labels

    t0 = time.perf_counter()
    engine = make_engine(system, threads)
    load_s = time.perf_counter() - t0
    engine(path_of(items[0]))  # warm-up (graph build, first allocation)

    preds = {}
    for i, it in enumerate(items):
        t = time.perf_counter()
        text = engine(path_of(it))
        preds[it["file"]] = {"text": text, "ms": (time.perf_counter() - t) * 1000}
        if (i + 1) % 25 == 0:
            print(f"[{system}] {i + 1}/{len(items)}", flush=True)
    target.write_text(json.dumps({"system": system, "load_s": load_s, "threads": threads, "preds": preds},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{system}] done: load {load_s:.1f}s, median {statistics.median(p['ms'] for p in preds.values()):.0f} ms/img")


def path_of(item: dict) -> str:
    f = item["file"]
    if f.startswith("test-images/"):  # real photos live in the repo-level test-images folder
        return str(HERE.parents[1] / f)
    return str(HERE / "data" / "images" / f)


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


def best_window_distance(ref: str, raw_text: str, max_lines: int = 3) -> int:
    """Edit distance between the reference and the best matching group of consecutive lines.

    Photos can carry unrelated text in the background; comparing the reference with the whole
    OCR output would count that text as errors. Choosing the best fragment (1..max_lines
    consecutive lines, as the reference phrase may wrap) measures only how well the phrase
    itself was read. If nothing was recognised the distance is len(ref).
    """
    lines = [norm(x) for x in raw_text.split("\n")]
    lines = [x for x in lines if x]
    best = len(ref)
    for i in range(len(lines)):
        for j in range(i + 1, min(len(lines), i + max_lines) + 1):
            best = min(best, Levenshtein.distance(ref, " ".join(lines[i:j])))
    return best


def metrics(labels: list[dict], raw: dict[str, Any]) -> list[dict]:
    """One row per (system, image) with cer_dist, ref_len, word_recall, n_words, ms."""
    rows = []
    for system, data in raw.items():
        for it in labels:
            pred = data["preds"].get(it["file"])
            if pred is None:
                continue
            hyp = norm(pred["text"])
            ref = norm(it["text"]) if it["group"] == "synthetic" else ""
            dist = best_window_distance(ref, pred["text"]) if ref else None
            words = it["words"]
            hits = sum(1 for w in words if w in hyp)
            rows.append({
                "system": system, "file": it["file"], "group": it["group"], "lang": it["lang"],
                "condition": it["condition"], "ref": it["text"], "hyp": pred["text"].replace("\n", " | "),
                "cer_dist": dist,
                "ref_len": len(ref) if ref else None,
                "exact": (dist == 0) if ref else None,
                "n_words_ref": len(words), "n_hits": hits,
                "word_recall": hits / len(words) if words else None,
                "n_words_pred": len(hyp.split()), "ms": pred["ms"],
            })
    return rows


def load_all() -> tuple[list[dict], dict[str, Any]]:
    labels = json.loads((HERE / "data" / "labels.json").read_text(encoding="utf-8"))
    raw = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(RAW.glob("*.json"))}
    return labels, raw


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--systems", nargs="+", default=list(SYSTEMS))
    r.add_argument("--threads", type=int, default=2)
    r.add_argument("--limit", type=int)
    r.add_argument("--force", action="store_true")
    r.add_argument("--low-priority", action="store_true", help="BelowNormal process priority")
    s = sub.add_parser("speed", help="timing only: every 6th image, run on an otherwise idle machine")
    s.add_argument("--systems", nargs="+", default=list(SYSTEMS))
    s.add_argument("--threads", type=int, default=6)
    a = ap.parse_args()

    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    if getattr(a, "low_priority", False):
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)

    labels = json.loads((HERE / "data" / "labels.json").read_text(encoding="utf-8"))
    if a.cmd == "speed":
        sample = labels[::6]
        out = HERE / "results" / "speed.json"
        res = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        for system in a.systems:
            try:
                engine = make_engine(system, a.threads)
                engine(path_of(sample[0]))  # warm-up
                ms = []
                for it in sample:
                    t = time.perf_counter()
                    engine(path_of(it))
                    ms.append((time.perf_counter() - t) * 1000)
                res[system] = {"threads": a.threads, "n": len(ms), "median_ms": statistics.median(ms),
                               "mean_ms": statistics.mean(ms)}
                out.write_text(json.dumps(res, indent=1), encoding="utf-8")
                print(f"[{system}] speed: median {res[system]['median_ms']:.0f} ms/img "
                      f"({a.threads} threads, {len(ms)} images)", flush=True)
            except Exception as e:
                print(f"[{system}] FAILED: {type(e).__name__}: {e}", flush=True)
        return
    for system in a.systems:
        try:
            run_system(system, labels, a.threads, a.limit, a.force)
        except Exception as e:  # keep going: one broken system must not lose the others
            print(f"[{system}] FAILED: {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    main()
