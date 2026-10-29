"""Build a ~40 image test set for the gallery: photos, photos with Russian text
and synthetic "chalkboard" images with a single word.

Photos come from Wikimedia Commons (free licenses, 1024 px thumbnails). The
boards are drawn locally with Pillow.

Run from ``backend``::

    uv run python scripts/fetch_test_images.py            # -> ../test-images
    uv run python scripts/fetch_test_images.py --dry-run  # only list what would be fetched
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia asks API clients to send a descriptive User-Agent.
USER_AGENT = "ai-search-gallery-test-set/0.1 (local development script; python-urllib)"
QUALITY = ' incategory:"Quality images"'

# (slug, search query, regex of titles to skip, how many files)
OBJECT_PHOTOS = [
    ("apple", "apple fruit" + QUALITY, r"Apple II|Apple Park|Headquarters|tree|iPhone|Mac", 2),
    ("banana", "banana" + QUALITY, r"", 2),
    ("cat", "cat" + QUALITY, r"", 2),
    ("dog", "dog" + QUALITY, r"", 2),
    ("bicycle", "bicycle" + QUALITY, r"", 2),
    ("sportscar", "sports car" + QUALITY, r"", 2),
    ("sunflower", "sunflower" + QUALITY, r"", 2),
    ("mountain-lake", "mountain lake" + QUALITY, r"", 2),
    ("coffee", "coffee cup" + QUALITY, r"", 2),
    ("pizza", "pizza" + QUALITY, r"", 2),
]

# Real photos that contain Russian (Cyrillic) text.
RUSSIAN_TEXT_PHOTOS = [
    ("ru-road-sign", "дорожный указатель", r"Tajikistan|Konibodom", 6),
    ("ru-shop-sign", "вывеска магазин", r"Säästumarket|Strategic|Book Look", 6),
]

# (file slug, text on the board). Pairs with the photos above on purpose:
# "Яблоко" on a board vs. a photo of an apple.
BOARDS = [
    ("apple_ru", "Яблоко"),
    ("cat_ru", "Кошка"),
    ("dog_ru", "Собака"),
    ("banana_ru", "Банан"),
    ("bicycle_ru", "Велосипед"),
    ("sunflower_ru", "Подсолнух"),
    ("coffee_ru", "Кофе"),
    ("pizza_ru", "Пицца"),
    ("apple_en", "Apple"),
    ("coffee_en", "Coffee"),
]


def http_get(url: str, retries: int = 5) -> bytes:
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def search_commons(query: str, limit: int) -> list[dict]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrsearch": query + " filetype:bitmap",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": "1024",
        "format": "json",
    }
    data = json.loads(http_get(API + "?" + urllib.parse.urlencode(params)))
    pages = sorted(
        data.get("query", {}).get("pages", {}).values(),
        key=lambda p: p.get("index", 0),
    )
    found = []
    for page in pages:
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            continue
        meta = info.get("extmetadata", {})
        found.append(
            {
                "title": page["title"].removeprefix("File:"),
                "url": info.get("thumburl") or info["url"],
                "license": meta.get("LicenseShortName", {}).get("value", ""),
            }
        )
    return found


def plan_downloads(groups) -> list[tuple[str, dict]]:
    seen: set[str] = set()
    plan: list[tuple[str, dict]] = []
    for slug, query, skip, count in groups:
        taken = 0
        for item in search_commons(query, limit=count * 4):
            if taken >= count:
                break
            if item["title"] in seen or (skip and re.search(skip, item["title"])):
                continue
            seen.add(item["title"])
            taken += 1
            suffix = Path(urllib.parse.urlparse(item["url"]).path).suffix.lower()
            if suffix not in (".jpg", ".jpeg", ".png"):
                suffix = ".jpg"
            plan.append((f"{slug}_{taken}{suffix}", item))
        if taken < count:
            print(f"  ! {slug}: found only {taken} of {count}", file=sys.stderr)
    return plan


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    print("  ! no TrueType font with Cyrillic found, boards may be unreadable", file=sys.stderr)
    return ImageFont.load_default()


def draw_board(path: Path, text: str) -> None:
    img = Image.new("RGB", (1024, 640), (38, 70, 56))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1023, 639), outline=(120, 82, 46), width=24)  # wooden frame
    font = load_font(190)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((1024 - (right - left)) / 2 - left, (640 - (bottom - top)) / 2 - top),
        text,
        fill=(238, 238, 228),
        font=font,
    )
    img.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "test-images",
        help="output directory (default: <repo>/test-images)",
    )
    parser.add_argument("--dry-run", action="store_true", help="list files, download nothing")
    args = parser.parse_args()

    print("Searching Wikimedia Commons ...")
    plan = plan_downloads(OBJECT_PHOTOS + RUSSIAN_TEXT_PHOTOS)

    args.out.mkdir(parents=True, exist_ok=True)
    for slug, text in BOARDS:
        draw_board(args.out / f"board_{slug}.png", text)
    print(f"Drew {len(BOARDS)} boards in {args.out}")

    for index, (filename, item) in enumerate(plan, 1):
        label = f"[{index}/{len(plan)}] {filename}  <-  {item['title']}  ({item['license']})"
        if args.dry_run:
            print("  would fetch", label)
            continue
        print("  fetching   ", label)
        (args.out / filename).write_bytes(http_get(item["url"]))
        time.sleep(0.5)  # be polite to Wikimedia

    total = len(plan) + len(BOARDS)
    print(f"\nDone: {total} files planned ({len(plan)} photos + {len(BOARDS)} boards) in {args.out}")


if __name__ == "__main__":
    main()
