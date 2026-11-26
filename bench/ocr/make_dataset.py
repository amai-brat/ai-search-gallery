"""Build the OCR test set.

* synthetic: Russian/English phrases with known text, drawn on plain colour or on real
  photos (Crossmodal-3600 images from the CLIP benchmark cache), five difficulty levels;
* real: photos of signs and "boards" from ``test-images`` with hand-written key words
  (``real_labels.json``);
* negatives: photos without text, to count junk recognitions.

    uv run python make_dataset.py            # writes data/images and data/labels.json

Everything is seeded, so the set is reproducible. Fonts are taken from the Windows font
folder by default (they are not redistributed with the repo); pass ``--font-dir`` elsewhere.
"""

from __future__ import annotations

import argparse
import io
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

RU = [
    "Продукты", "Аптека", "Кофе с собой", "Выход", "Скидки до 50%", "Пекарня №1",
    "Часы работы 9-21", "Магазин Радуга", "Вход со двора", "Горячие пирожки",
    "Не курить", "Касса", "Парикмахерская", "Мясо и рыба", "Ремонт обуви",
    "Тел. 8-800-555-35-35", "Улица Ленина, 15", "Чай, кофе, сладости", "Ключи за 5 минут",
    "Цветы", "Хлеб", "Бар у моста", "Левый берег", "Осторожно, ступенька",
    "Станция метро", "Двуречье", "Книжный магазин", "Электротовары", "Работаем без выходных",
    "Добро пожаловать",
]
EN = [
    "Open", "Coffee to go", "Pharmacy", "Exit", "Sale up to 50%", "Fresh bakery",
    "Opening hours 9-21", "Main Street 15", "No parking", "Welcome", "Bar and grill",
    "Tel. 555-0199", "Book store", "Fish and chips", "Keep out", "Shoe repair",
    "Hot dogs", "Flower shop", "Cash only", "Central station", "Open 24 hours",
    "Free Wi-Fi", "Ice cream", "Beware of the dog", "Car wash", "Grand Hotel",
    "Pizza and pasta", "Take away", "City Museum", "Bike rental",
]
CONDITIONS = ["clean", "photo", "small", "rotated", "degraded"]
FONT_NAMES = ["arial.ttf", "arialbd.ttf", "times.ttf", "calibri.ttf", "verdana.ttf",
              "segoeui.ttf", "georgia.ttf", "impact.ttf", "tahoma.ttf", "cour.ttf"]
W, H = 1024, 768


def find_fonts(font_dir: Path) -> list[Path]:
    fonts = [font_dir / n for n in FONT_NAMES if (font_dir / n).exists()]
    if not fonts:
        raise SystemExit(f"No fonts with Cyrillic found in {font_dir}; use --font-dir")
    return fonts


def background(kind: str, photos: list[Path], rng: random.Random) -> Image.Image:
    if kind == "clean":
        base = rng.choice([(255, 255, 255), (245, 240, 220), (230, 238, 250), (30, 30, 30), (20, 60, 120)])
        return Image.new("RGB", (W, H), base)
    img = Image.open(rng.choice(photos)).convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((left, top, left + W, top + H))


def contrast_colors(bg: Image.Image, box: tuple[int, int, int, int]) -> tuple[tuple, tuple]:
    patch = np.asarray(bg.crop(box).convert("L"))
    dark = patch.mean() < 128
    return ((255, 255, 255), (0, 0, 0)) if dark else ((0, 0, 0), (255, 255, 255))


def render(text: str, cond: str, font_path: Path, photos: list[Path], rng: random.Random) -> Image.Image:
    bg = background(cond, photos, rng)
    height_frac = {"clean": 0.09, "photo": 0.08, "small": 0.035, "rotated": 0.08, "degraded": 0.06}[cond]
    size = max(14, round(H * height_frac * rng.uniform(0.9, 1.15)))
    font = ImageFont.truetype(str(font_path), size)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    l, t, r, b = probe.textbbox((0, 0), text, font=font, stroke_width=2)
    tw, th = r - l, b - t
    while tw > W * 0.9 and size > 14:  # long phrases: shrink to fit the canvas
        size = int(size * 0.9)
        font = ImageFont.truetype(str(font_path), size)
        l, t, r, b = probe.textbbox((0, 0), text, font=font, stroke_width=2)
        tw, th = r - l, b - t

    pad = 6
    layer = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    x0 = rng.randint(0, max(0, W - tw - 2 * pad - 1))
    y0 = rng.randint(0, max(0, H - th - 2 * pad - 1))
    fill, stroke = contrast_colors(bg, (x0, y0, x0 + tw + 2 * pad, y0 + th + 2 * pad))
    if cond == "clean":
        fill = (255, 255, 255) if np.asarray(bg.convert("L")).mean() < 128 else (0, 0, 0)
    alpha = 190 if cond == "degraded" else 255
    ImageDraw.Draw(layer).text(
        (pad - l, pad - t), text, font=font, fill=fill + (alpha,),
        stroke_width=0 if cond == "clean" else 2, stroke_fill=stroke + (alpha,),
    )
    if cond == "rotated":
        layer = layer.rotate(rng.choice([-1, 1]) * rng.uniform(10, 25), expand=True, resample=Image.BICUBIC)
        x0 = min(x0, max(0, W - layer.width)); y0 = min(y0, max(0, H - layer.height))
    bg.paste(layer, (x0, y0), layer)

    if cond == "degraded":
        bg = bg.filter(ImageFilter.GaussianBlur(rng.uniform(1.2, 2.2)))
        arr = np.asarray(bg).astype(np.float32)
        arr += np.random.default_rng(rng.randint(0, 2**31)).normal(0, 10, arr.shape)
        bg = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        buf = io.BytesIO(); bg.save(buf, "JPEG", quality=25); buf.seek(0)
        bg = Image.open(buf).convert("RGB")
    return bg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=15, help="images per language x condition")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--font-dir", type=Path, default=Path("C:/Windows/Fonts"))
    ap.add_argument("--photos", type=Path, default=Path.home() / "models/datasets/xm3600/images",
                    help="folder of .jpg photos used as backgrounds")
    ap.add_argument("--test-images", type=Path, default=REPO / "test-images")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    fonts = find_fonts(a.font_dir)
    photos = sorted(a.photos.glob("*.jpg"))
    if len(photos) < 30:
        raise SystemExit(f"Need photos for backgrounds in {a.photos} (run the CLIP benchmark once)")
    photos = rng.sample(photos, 60)

    out = HERE / "data" / "images"
    out.mkdir(parents=True, exist_ok=True)
    labels = []

    for lang, pool in (("ru", RU), ("en", EN)):
        for cond in CONDITIONS:
            phrases = rng.sample(pool, len(pool))
            for i in range(a.per_cell):
                text = phrases[i % len(phrases)]
                img = render(text, cond, rng.choice(fonts), photos, rng)
                name = f"syn_{lang}_{cond}_{i:02d}." + ("jpg" if cond == "degraded" else "png")
                img.save(out / name, quality=90) if name.endswith("jpg") else img.save(out / name)
                words = [w for w in "".join(c if c.isalnum() else " " for c in text.lower().replace("ё", "е")).split()]
                labels.append({"file": name, "group": "synthetic", "lang": lang, "condition": cond,
                               "text": text, "words": words})

    real = json.loads((HERE / "real_labels.json").read_text(encoding="utf-8"))
    missing = []
    for group, key in (("real_photo", "photos"), ("real_board", "boards")):
        for item in real[key]:
            src = a.test_images / item["file"]
            if not src.exists():
                missing.append(item["file"]); continue
            labels.append({"file": f"test-images/{item['file']}", "group": group, "lang": item["lang"], "condition": group,
                           "text": " ".join(item["words"]), "words": item["words"]})
    for f in real["negatives"]:
        src = a.test_images / f
        if src.exists():
            labels.append({"file": f"test-images/{f}", "group": "negative", "lang": "-", "condition": "negative",
                           "text": "", "words": []})
        else:
            missing.append(f)
    if missing:
        print("WARNING: not found in test-images (run backend/scripts/fetch_test_images.py):", missing)

    (HERE / "data" / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(Counter(l["group"] for l in labels), "->", HERE / "data")


if __name__ == "__main__":
    main()
