"""Benchmark of multilingual CLIP-style models for text -> image gallery search.

Every model is measured in its own subprocess so that RAM numbers are not
polluted by the previously loaded models.

    uv run python -m bench.clip_bench run --models ViT-B-16-SigLIP2 --n-images 1000
    uv run python -m bench.clip_bench worker --model ViT-B-16-SigLIP2 --out results/cpu/raw

What is measured (text query -> ranked images, one correct image per caption):

* quality: Recall@1/5/10, NDCG@10, MRR over the whole pool and per language;
* image encoding cost per image (decode+resize on CPU, then the model forward);
* text query latency with batch size 1 (this is what a search request costs);
* RAM: held by the loaded model and peak during encoding; average CPU cores busy.
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

RECALL_KS = (1, 5, 10)
NDCG_K = 10

DEFAULT_MODELS = [
    "xlm-roberta-base-ViT-B-32",
    "ViT-B-16-SigLIP2",  # the model the app uses now
    "ViT-B-32-SigLIP2-256",
    "ViT-SO400M-16-SigLIP2-384",
    "nllb-clip-base-siglip",
]


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def retrieval_metrics(
    text_emb: np.ndarray, image_emb: np.ndarray, text_img: np.ndarray
) -> dict[str, float]:
    """Rank all images for every caption by cosine similarity (inputs L2-normalised).

    The rank of the ground-truth image is the number of images scoring strictly
    higher; there is exactly one relevant image per caption, so IDCG = 1.
    """
    sims = text_emb @ image_emb.T  # (T, N)
    gt = sims[np.arange(len(text_img)), text_img]
    rank = (sims > gt[:, None]).sum(axis=1)  # 0 = best

    out = {f"Recall@{k}": float((rank < k).mean()) for k in RECALL_KS}
    in_top = rank < NDCG_K
    out[f"NDCG@{NDCG_K}"] = float(np.where(in_top, 1.0 / np.log2(rank + 2), 0.0).mean())
    out["MRR"] = float((1.0 / (rank + 1)).mean())
    return out


# --------------------------------------------------------------------------- #
# resource sampling
# --------------------------------------------------------------------------- #
class ResourceMonitor:
    """Samples the process RSS in a thread and CPU time at start/stop."""

    def __init__(self, interval: float = 0.02) -> None:
        import psutil

        self._proc = psutil.Process()
        self._interval = interval
        self._stop = threading.Event()
        self.peak_rss = 0
        self.cores_busy = 0.0

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.peak_rss = max(self.peak_rss, self._proc.memory_info().rss)
            time.sleep(self._interval)

    def __enter__(self) -> "ResourceMonitor":
        t = self._proc.cpu_times()
        self._cpu0 = t.user + t.system
        self._wall0 = time.perf_counter()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()
        t = self._proc.cpu_times()
        wall = time.perf_counter() - self._wall0
        self.cores_busy = (t.user + t.system - self._cpu0) / wall if wall else 0.0
        self.peak_rss = max(self.peak_rss, self._proc.memory_info().rss)


# --------------------------------------------------------------------------- #
# one model
# --------------------------------------------------------------------------- #
def run_worker(
    model_name: str,
    out_dir: Path,
    n_images: int,
    langs: list[str],
    device: str,
    seed: int,
    image_batch: int,
    text_batch: int,
    query_runs: int,
) -> dict:
    import open_clip
    import psutil
    import torch
    from PIL import Image

    from bench.data import load_retrieval_set

    proc = psutil.Process()
    data = load_retrieval_set(n_images=n_images, langs=langs, seed=seed)
    n_img, n_txt = len(data.image_paths), len(data.texts)
    print(f"[{model_name}] {n_img} images, {n_txt} captions {langs}, device={device}")

    def sync() -> None:
        if device == "cuda":
            torch.cuda.synchronize()

    # ---- load ---------------------------------------------------------------
    pretrained = next(tag for name, tag in open_clip.list_pretrained() if name == model_name)
    gc.collect()
    rss_before = proc.memory_info().rss
    t0 = time.perf_counter()
    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained, require_pretrained=True, device=device
    )
    model.eval()
    tokenizer = open_clip.get_tokenizer(model_name)
    load_s = time.perf_counter() - t0
    gc.collect()
    model_ram_mib = (proc.memory_info().rss - rss_before) / 2**20
    n_params_m = sum(p.numel() for p in model.parameters()) / 1e6
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    def norm(x: torch.Tensor) -> torch.Tensor:
        return x / x.norm(dim=-1, keepdim=True)

    def load_batch(paths: list[Path]) -> torch.Tensor:
        return torch.stack([preprocess(Image.open(p).convert("RGB")) for p in paths])

    # ---- images: warm-up, then the full pass is the measurement ---------------
    with torch.no_grad():
        warm = load_batch(data.image_paths[:image_batch]).to(device)
        for _ in range(2):
            model.encode_image(warm)
        sync()

        embeds, pre_s, fwd_s = [], 0.0, 0.0
        with ResourceMonitor() as mon_img:
            for i in range(0, n_img, image_batch):
                t = time.perf_counter()
                x = load_batch(data.image_paths[i : i + image_batch]).to(device)
                pre_s += time.perf_counter() - t
                t = time.perf_counter()
                e = norm(model.encode_image(x))
                sync()
                fwd_s += time.perf_counter() - t
                embeds.append(e.float().cpu())
        image_emb = torch.cat(embeds).numpy()

        # ---- texts: single-query latency (what one search request costs) -----
        rng = np.random.default_rng(seed)
        sample = [data.texts[i] for i in rng.choice(n_txt, query_runs + 3, replace=False)]
        lat = []
        for i, q in enumerate(sample):
            t = time.perf_counter()
            e = model.encode_text(tokenizer([q]).to(device))
            sync()
            if i >= 3:  # first 3 are warm-up
                lat.append((time.perf_counter() - t) * 1000)

        # ---- texts: all captions in batches (for the metrics) ----------------
        t_embeds = []
        with ResourceMonitor() as mon_txt:
            t = time.perf_counter()
            for i in range(0, n_txt, text_batch):
                tok = tokenizer(data.texts[i : i + text_batch]).to(device)
                t_embeds.append(norm(model.encode_text(tok)).float().cpu())
            sync()
            txt_batch_s = time.perf_counter() - t
        text_emb = torch.cat(t_embeds).numpy()

    # ---- quality ------------------------------------------------------------
    overall = retrieval_metrics(text_emb, image_emb, data.text_img)
    per_lang = {}
    for lang in langs:
        m = data.text_lang == lang
        per_lang[lang] = retrieval_metrics(text_emb[m], image_emb, data.text_img[m])

    result = {
        "model": model_name,
        "pretrained": pretrained,
        "device": device,
        "n_images": n_img,
        "n_captions": n_txt,
        "langs": langs,
        "chance_recall@1": 1 / n_img,
        "embed_dim": int(image_emb.shape[1]),
        "params_m": round(n_params_m, 1),
        "load_s": round(load_s, 1),
        "model_ram_mib": round(model_ram_mib),
        "img_preprocess_ms": pre_s / n_img * 1000,
        "img_forward_ms": fwd_s / n_img * 1000,
        "img_total_ms": (pre_s + fwd_s) / n_img * 1000,
        "img_peak_rss_mib": mon_img.peak_rss / 2**20,
        "img_cpu_cores_busy": mon_img.cores_busy,
        "query_ms_median": statistics.median(lat),
        "query_ms_p95": float(np.percentile(lat, 95)),
        "txt_batch_ms_per_text": txt_batch_s / n_txt * 1000,
        "txt_peak_rss_mib": mon_txt.peak_rss / 2**20,
        "txt_cpu_cores_busy": mon_txt.cores_busy,
        **overall,
        "per_lang": per_lang,
        "env": {
            "torch": torch.__version__,
            "open_clip": open_clip.__version__,
            "torch_threads": torch.get_num_threads(),
            "cpu": platform.processor(),
            "cpu_count": psutil.cpu_count(logical=False),
            "ram_gib": round(psutil.virtual_memory().total / 2**30, 1),
            "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
        },
    }
    if device == "cuda":
        result["cuda_peak_mib"] = torch.cuda.max_memory_allocated() / 2**20

    # a working model is far above chance (10 / n_img); near chance means broken labels
    if result["Recall@10"] < min(0.5, 3 * 10 / n_img):
        print(f"[{model_name}] WARNING: Recall@10={result['Recall@10']:.3f} is close to chance "
              f"({10 / n_img:.3f}); check the caption->image labels.")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{model_name}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"[{model_name}] R@1={result['Recall@1']:.3f} R@10={result['Recall@10']:.3f} "
          f"img={result['img_total_ms']:.0f} ms/img query={result['query_ms_median']:.0f} ms")
    return result


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def run_all(
    models: list[str],
    out_dir: Path,
    n_images: int = 1000,
    langs: tuple[str, ...] = ("en", "ru"),
    device: str = "cpu",
    seed: int = 0,
    image_batch: int = 8,
    text_batch: int = 32,
    query_runs: int = 30,
    force: bool = False,
) -> list[dict]:
    """Run every model in a fresh subprocess; finished models are cached as JSON."""
    raw = out_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for model in models:
        target = raw / f"{model}.json"
        if target.exists() and not force:
            cached = json.loads(target.read_text(encoding="utf-8"))
            if cached["n_images"] == n_images and cached["langs"] == list(langs):
                print(f"[{model}] cached, skipping (force=True to rerun)")
                continue
        cmd = [
            sys.executable, "-u", "-m", "bench.clip_bench", "worker",
            "--model", model, "--out", str(raw), "--n-images", str(n_images),
            "--langs", *langs, "--device", device, "--seed", str(seed),
            "--image-batch", str(image_batch), "--text-batch", str(text_batch),
            "--query-runs", str(query_runs),
        ]
        with subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8"
        ) as p:
            for line in p.stdout:  # type: ignore[union-attr]
                if line.strip():
                    print(line, end="")
            if p.wait() != 0:
                print(f"[{model}] FAILED (exit code {p.returncode})")
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(raw.glob("*.json"))]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--n-images", type=int, default=1000)
        p.add_argument("--langs", nargs="+", default=["en", "ru"])
        p.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--image-batch", type=int, default=8)
        p.add_argument("--text-batch", type=int, default=32)
        p.add_argument("--query-runs", type=int, default=30)

    r = sub.add_parser("run", help="benchmark several models, one subprocess each")
    r.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    r.add_argument("--out", type=Path, default=Path("results/cpu"))
    r.add_argument("--force", action="store_true")
    common(r)

    w = sub.add_parser("worker", help="benchmark a single model in this process")
    w.add_argument("--model", required=True)
    w.add_argument("--out", type=Path, required=True)
    common(w)

    a = ap.parse_args(argv)
    if a.cmd == "run":
        run_all(a.models, a.out, a.n_images, tuple(a.langs), a.device, a.seed,
                a.image_batch, a.text_batch, a.query_runs, a.force)
    else:
        run_worker(a.model, a.out, a.n_images, a.langs, a.device, a.seed,
                   a.image_batch, a.text_batch, a.query_runs)


if __name__ == "__main__":
    main()
