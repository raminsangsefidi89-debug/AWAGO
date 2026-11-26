"""Market + news API endpoints (addendum E)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.services.drivers import (
    lead_lag,
    regime_dependence,
    rolling_correlation,
)
from app.services.markets.service import demo_quote, market_overview
from app.services.news.features import news_value_test

router = APIRouter(prefix="/markets", tags=["markets"])

_DEMO_NEWS: list[dict] = [
    {
        "id": 1,
        "source": "demo",
        "tier": "unrated",
        "url": "",
        "title": "داده نمایشی: قیمت طلا در بازار جهانی افزایش یافت",
        "snippet": "این خبر نمایشی (Demo) است و به هیچ منبع واقعی متصل نیست.",
        "published_at": "2026-11-26T06:30:00+00:00",
        "fetched_at": "2026-11-26T06:35:00+00:00",
        "available_at": "2026-11-26T06:35:00+00:00",
        "language": "fa",
        "topics": ["gold"],
        "sentiment": 0.5,
        "cluster_id": 0,
        "is_demo": True,
    },
    {
        "id": 2,
        "source": "demo",
        "tier": "unrated",
        "url": "",
        "title": "داده نمایشی: تنش‌های سیاستی بر بازار ارز",
        "snippet": "این خبر نمایشی (Demo) است.",
        "published_at": "2026-11-26T04:00:00+00:00",
        "fetched_at": "2026-11-26T04:05:00+00:00",
        "available_at": "2026-11-26T04:05:00+00:00",
        "language": "fa",
        "topics": ["usd", "iran_market", "geopolitics"],
        "sentiment": -0.4,
        "cluster_id": 1,
        "is_demo": True,
    },
]


@router.get("/overview")
def overview(prefer_toman: bool = Query(default=True)) -> dict[str, Any]:
    return market_overview(prefer_toman=prefer_toman)


@router.get("/news")
def news_feed(topic: str | None = None, language: str | None = None) -> dict[str, Any]:
    items = list(_DEMO_NEWS)
    if topic:
        items = [it for it in items if topic in (it.get("topics") or [])]
    if language:
        items = [it for it in items if it.get("language") == language]
    return {
        "data_mode": "demo",
        "coverage_note": (
            "پوشش کامل اخبار ادعا نمی‌شود — منابع فعال و آخرین زمان دریافت نمایش داده می‌شود"
        ),
        "active_sources": ["demo"],
        "last_successful_fetch": None,
        "items": items,
    }


@router.get("/news/value")
def news_value() -> dict[str, Any]:
    """Honest news-value verdict panel (with-news vs without-news)."""
    verdicts = [
        news_value_test([0.5] * 30, [0.52] * 30, "XAU_USD", 1).__dict__,
        news_value_test([0.48] * 30, [0.47] * 30, "USD_IRR_FREE", 1).__dict__,
    ]
    for v in verdicts:
        v["data_mode"] = "demo"
    return {
        "method": "walk-forward + Diebold-Mariano on paired losses (same model, same splits)",
        "verdicts": verdicts,
        "policy": "اگر خبرها کمک نکنند، صرفاً به‌عنوان زمینه نمایش داده می‌شوند — هرگز در مدل قهرمان",
    }


@router.get("/drivers")
def drivers(instrument: str = "XAU_USD") -> dict[str, Any]:
    """Driver analysis: rolling correlations + lead-lag + permutation importance."""
    rng_target = demo_quote(instrument)
    target = [float(rng_target["value"]) * (1 + 0.0001 * i) for i in range(120)]
    out: dict[str, Any] = {"instrument": instrument, "data_mode": "demo", "series": {}}
    brent_series: list[float] = []
    for did in ("USD_IRR_FREE", "US10Y_REAL", "BRENT", "VIX", "XAG_USD"):
        dq = demo_quote(did)
        s = [float(dq["value"]) * (1 + 0.0002 * ((i * 7) % 13 - 6)) for i in range(120)]
        if did == "BRENT":
            brent_series = s
        out["series"][did] = {
            "rolling_corr": rolling_correlation(target, s, window=40)[-1][1],
            "lead_lag": lead_lag(target, s, max_lag=3),
        }
    out["regime_dependence"] = regime_dependence(
        target,
        brent_series,
        ["high_vol" if i % 2 else "low_vol" for i in range(len(target))],
    )
    out["permutation_importance"] = [
        {"feature": "USD_IRR_FREE", "importance": 0.021},
        {"feature": "US10Y_REAL", "importance": -0.004},
    ]
    out["caution"] = (
        "همبستگی ≠ علیت — سری‌های رونددار می‌توانند همبستگی کاذب نشان دهند (spurious correlation)"
    )
    return out
