"""Figures for bench/e2e/README.md: speed before/after and OCR quality before/after.

Run from the repo root (uses the backend environment plus matplotlib)::

    python -m uv run --project backend --with matplotlib --with rapidfuzz python bench/e2e/make_figures.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"
sys.path.insert(0, str(HERE.parent / "ocr"))

BEFORE, AFTER = "#eb6834", "#2a78d6"  # validated pair (dataviz palette, slots 2 and 1)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OCR_BEFORE, OCR_AFTER = "paddle-current", "rapid-eslav-960-nodil"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})


def load(label: str) -> dict:
    return json.loads((HERE / "results" / f"{label}.json").read_text(encoding="utf-8"))


def median(result: dict, key: str, group: str | None = None) -> float:
    return statistics.median(r[key] for r in result["images"] if group in (None, r["group"]))


def grouped_barh(ax, labels, before, after, fmt, legend=("Было", "Стало")):
    """Horizontal grouped bars: 'before' above 'after' for every category."""
    h, gap = 0.36, 0.04
    ys = range(len(labels))
    for i, (b, a) in enumerate(zip(before, after)):
        ax.barh(i - (h + gap) / 2, b, h, color=BEFORE, label=legend[0] if i == 0 else None)
        ax.barh(i + (h + gap) / 2, a, h, color=AFTER, label=legend[1] if i == 0 else None)
        ax.text(b, i - (h + gap) / 2, " " + fmt(b), va="center", color=INK2, fontsize=10)
        ax.text(a, i + (h + gap) / 2, " " + fmt(a), va="center", color=INK2, fontsize=10)
    ax.set_yticks(list(ys), labels)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.13), ncol=2, frameon=False)


def speed_figure(base: dict, new: dict) -> None:
    groups = [("small", "Фото до 1280 px"), ("synthetic", "Картинки 1024×768"),
              ("phone", "Фото с телефона, 4032 px"), (None, "Все 224 картинки")]
    before = [median(base, "total_ms", g) / 1000 for g, _ in groups]
    after = [median(new, "total_ms", g) / 1000 for g, _ in groups]
    labels = [f"{name}\n×{b / a:.0f} быстрее" for (_, name), b, a in zip(groups, before, after)]

    fig, ax = plt.subplots(figsize=(9, 4.6))
    grouped_barh(ax, labels, before, after, lambda v: f"{v:.2f} с")
    ax.set_xlabel("Медианное время индексации одной картинки, с (меньше — лучше)")
    ax.set_xlim(0, max(before) * 1.15)
    fig.suptitle("Индексация: время на картинку", x=0.02, ha="left", fontsize=14, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "speed_per_image.png", dpi=160)
    plt.close(fig)


def stages_figure(base: dict, new: dict) -> None:
    rows = [("clip_ms", None, "CLIP, все картинки"), ("ocr_ms", None, "OCR, все картинки"),
            ("ocr_ms", "phone", "OCR, фото с телефона"), ("query", None, "Поисковый запрос")]
    before, after, labels = [], [], []
    for key, group, name in rows:
        if key == "query":
            b, a = statistics.median(base["query_ms"]), statistics.median(new["query_ms"])
        else:
            b, a = median(base, key, group), median(new, key, group)
        before.append(b)
        after.append(a)
        labels.append(f"{name}\n×{b / a:.0f} быстрее")

    fig, ax = plt.subplots(figsize=(9, 4.6))
    grouped_barh(ax, labels, before, after, lambda v: f"{v:,.0f} мс".replace(",", " "))
    ax.set_xlabel("Медиана, мс (меньше — лучше)")
    ax.set_xlim(0, max(before) * 1.18)
    fig.suptitle("Время по этапам", x=0.02, ha="left", fontsize=14, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "stages.png", dpi=160)
    plt.close(fig)


def ocr_quality() -> dict[str, dict[str, float]]:
    import ocr_bench

    labels, raw = ocr_bench.load_all()
    rows = ocr_bench.metrics(labels, {s: raw[s] for s in (OCR_BEFORE, OCR_AFTER)})
    out: dict[str, dict[str, float]] = {}
    for system in (OCR_BEFORE, OCR_AFTER):
        mine = [r for r in rows if r["system"] == system]

        def recall(group: str, lang: str | None = None) -> float:
            vals = [r["word_recall"] for r in mine if r["group"] == group
                    and lang in (None, r["lang"]) and r["word_recall"] is not None]
            return statistics.mean(vals)

        syn = [r for r in mine if r["cer_dist"] is not None]
        out[system] = {
            "synthetic_ru": recall("synthetic", "ru"),
            "synthetic_en": recall("synthetic", "en"),
            "real_photo": recall("real_photo"),
            "real_board": recall("real_board"),
            "cer": sum(r["cer_dist"] for r in syn) / sum(r["ref_len"] for r in syn),
            "junk": statistics.mean(r["n_words_pred"] for r in mine if r["group"] == "negative"),
            "ms": statistics.median(r["ms"] for r in mine),
        }
    return out


def quality_figure(q: dict[str, dict[str, float]]) -> None:
    keys = [("synthetic_ru", "Синтетика, русский (75)"), ("synthetic_en", "Синтетика, английский (75)"),
            ("real_photo", "Реальные фото (12)"), ("real_board", "Доски с надписью (10)")]
    before = [q[OCR_BEFORE][k] * 100 for k, _ in keys]
    after = [q[OCR_AFTER][k] * 100 for k, _ in keys]

    fig, ax = plt.subplots(figsize=(9, 4.6))
    grouped_barh(ax, [name for _, name in keys], before, after, lambda v: f"{v:.1f}%",
                 legend=("PaddleOCR (было)", "RapidOCR / ONNX (стало)"))
    ax.set_xlabel("Найдено слов, % (больше — лучше)")
    ax.set_xlim(0, 112)
    fig.suptitle("OCR: качество распознавания", x=0.02, ha="left", fontsize=14, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "ocr_quality.png", dpi=160)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    base, new = load("baseline"), load("onnx")
    speed_figure(base, new)
    stages_figure(base, new)
    q = ocr_quality()
    quality_figure(q)
    (HERE / "results" / "ocr_quality.json").write_text(json.dumps(q, indent=1), encoding="utf-8")
    for system, m in q.items():
        print(system, {k: round(v, 3) for k, v in m.items()})
    print(f"figures in {OUT}")


if __name__ == "__main__":
    main()
