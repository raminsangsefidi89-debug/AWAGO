"""Inspectable lexicon sentiment (FA + EN). Model name/version persisted.

Honest scope: a small curated lexicon with negation handling. It is a
*baseline heuristic* — quality is validated by tests (sanity checks on
known phrases), not advertised as a trained model. Score in [-1, 1].
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.news.normalize import normalize_fa

MODEL_NAME = "lexicon-fa-en"
MODEL_VERSION = "1"

POS = {
    "رشد",
    "افزایش",
    "جهش",
    "صعود",
    "سود",
    "بهبود",
    "مثبت",
    "توافق",
    "کاهش تنش",
    "gain",
    "rise",
    "rally",
    "surge",
    "boost",
    "positive",
    "deal",
    "agreement",
    "rebound",
}
NEG = {
    "سقوط",
    "کاهش",
    "ریزش",
    "ضرر",
    "بحران",
    "تحریم",
    "تنش",
    "جنگ",
    "منفی",
    "رکود",
    "تورم",
    "fall",
    "drop",
    "crash",
    "plunge",
    "loss",
    "crisis",
    "sanction",
    "tension",
    "war",
    "negative",
    "recession",
    "inflation",
    "collapse",
}
NEGATORS = {"نه", "ن", "بدون", "not", "no", "never", "without"}


@dataclass(frozen=True)
class SentimentResult:
    score: float  # [-1, 1]
    positive_hits: list[str]
    negative_hits: list[str]
    model: str = f"{MODEL_NAME}/{MODEL_VERSION}"


def score_sentiment(text: str) -> SentimentResult:
    t = normalize_fa(text)
    words = re.split(r"[^\w\u0600-\u06ff]+", t)
    pos_hits: list[str] = []
    neg_hits: list[str] = []
    for i, w in enumerate(words):
        if not w:
            continue
        negated = any(words[j] in NEGATORS for j in range(max(0, i - 2), i))
        if w in POS:
            (neg_hits if negated else pos_hits).append(w)
        elif w in NEG:
            (pos_hits if negated else neg_hits).append(w)
    total = len(pos_hits) + len(neg_hits)
    score = 0.0 if total == 0 else (len(pos_hits) - len(neg_hits)) / total
    return SentimentResult(round(score, 4), pos_hits, neg_hits)
