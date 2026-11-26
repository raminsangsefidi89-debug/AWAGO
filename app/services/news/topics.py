"""Rules-first topic tagging (FA+EN), inspectable keyword lexicon.

Keyword-layer only (P1); a transformer classifier would live in the `full`
profile with its model name+version persisted. Deterministic and testable.
"""

from __future__ import annotations

from app.services.news.normalize import normalize_fa

TOPIC_LEXICON: dict[str, list[str]] = {
    "gold": ["طلا", "سکه", "gold", "xau", "اونس", "ounce", "امامی", "emami"],
    "usd": ["دلار", "dollar", "usd", "ارز", "exchange rate", "نرخ ارز", "fx"],
    "iran_market": ["بازار آزاد", "نرخ توافقی", "نیما", "nima", "تومن", "toman", "ریال", "rial"],
    "sanctions": ["تحریم", "sanction", "embargo", "ofac", "fatf"],
    "oil": ["نفت", "oil", "brent", "اوپک", "opec", "wti"],
    "fed": ["فدرال رزرو", "federal reserve", "fed ", "interest rate", "نرخ بهره", "powell"],
    "inflation": ["تورم", "inflation", "cpi", "شاخص قیمت"],
    "geopolitics": ["جنگ", "war", "geopolit", "تنش", "invasion", "خاورمیانه", "middle east"],
    "domestic_policy": [
        "بانک مرکزی",
        "central bank",
        "یارانه",
        "budget",
        "بودجه",
        "government",
        "دولت",
    ],
    "crypto": ["بیت کوین", "bitcoin", "tether", "تتر", "crypto", "ارز دیجیتال", "btc", "usdt"],
}


def tag_topics(title: str, snippet: str = "") -> list[str]:
    text = normalize_fa(f"{title} {snippet}")
    hits = []
    for topic, kws in TOPIC_LEXICON.items():
        for kw in kws:
            if normalize_fa(kw) in text:
                hits.append(topic)
                break
    return hits
