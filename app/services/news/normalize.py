"""Persian/English text normalization (addendum C).

* ZWNJ preserved where meaningful but normalized (U+200C canonical).
* Arabic/Persian digits -> ASCII for parsing; display uses Persian digits.
* ي -> ی, ك -> ک (common variants), strip tashkeel, collapse whitespace.
"""

from __future__ import annotations

import re
import unicodedata

ZWNJ = "\u200c"
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_TASHKEEL = re.compile(r"[\u064B-\u065F\u0670]")
_WS = re.compile(r"\s+")

# conservative normalizations (ordered)
_REPLACEMENTS = [
    ("\u064a", "\u06cc"),  # Arabic yeh -> Farsi yeh
    ("\u0643", "\u06a9"),  # Arabic kaf -> Farsi kaf
    ("\u0649", "\u06cc"),  # alef maqsura
    ("\u200d", ZWNJ),  # ZWJ -> ZWNJ
]


def to_ascii_digits(text: str) -> str:
    out = []
    for ch in text:
        if ch in _AR_DIGITS:
            out.append(str(_AR_DIGITS.index(ch)))
        elif ch in _FA_DIGITS:
            out.append(str(_FA_DIGITS.index(ch)))
        else:
            out.append(ch)
    return "".join(out)


def normalize_fa(text: str) -> str:
    """Canonical form for FA matching/dedup/tokenization."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    for a, b in _REPLACEMENTS:
        t = t.replace(a, b)
    t = _TASHKEEL.sub("", t)
    t = to_ascii_digits(t)
    t = t.replace("\u200e", "").replace("\u200f", "")
    t = _WS.sub(" ", t).strip().lower()
    return t


def detect_language(text: str) -> str:
    """Very small script-based detector: fa if Arabic-script letters dominate."""
    if not text:
        return "unknown"
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "unknown"
    arabic = sum(1 for c in letters if "\u0600" <= c <= "\u06ff")
    return "fa" if arabic / len(letters) > 0.4 else "en"


def tokenize(text: str) -> list[str]:
    t = normalize_fa(text)
    return [w for w in re.split(r"[^\w\u0600-\u06ff]+", t) if len(w) > 1]
