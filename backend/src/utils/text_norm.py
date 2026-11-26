"""Text normalization for OCR search: case folding and word stems.

Replaces Postgres' ``to_tsvector('russian' | 'english', ...)``: every word is
reduced to its stem by the Snowball stemmer of its alphabet (Cyrillic words by
the Russian one, the rest by the English one), so "яблоки" finds "Яблоко" and
"apples" finds "Apple".
"""

import re
import unicodedata
from functools import lru_cache

import snowballstemmer

_WORD = re.compile(r"\w+")
_CYRILLIC = re.compile(r"[а-я]")
_RU = snowballstemmer.stemmer("russian")
_EN = snowballstemmer.stemmer("english")


def normalize(text: str) -> str:
    """Lower case, ё -> е, composed Unicode."""
    return unicodedata.normalize("NFC", text).lower().replace("ё", "е")


@lru_cache(maxsize=65536)
def stem(word: str) -> str:
    """Stem of one normalized word."""
    stemmer = _RU if _CYRILLIC.search(word) else _EN
    return stemmer.stemWord(word)


def stems(text: str) -> list[str]:
    """Stems of all words of a text, in order."""
    return [stem(w) for w in _WORD.findall(normalize(text))]


def stems_column(text: str) -> str:
    """Value of images.ocr_stems: stems separated and surrounded by spaces, so
    a stem is matched as a whole with LIKE '% stem %'."""
    words = dict.fromkeys(stems(text))  # unique, order kept
    return f" {' '.join(words)} " if words else ""
