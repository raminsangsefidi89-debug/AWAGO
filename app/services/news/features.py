"""Point-in-time news features + value test (addendum C/D).

POINT-IN-TIME RULE (leakage-critical):
    available_at = max(published_at, fetched_at)
Only items with ``available_at <= window_end`` may contribute to features for
that window. Aggregates over past windows only — enforced + negative-tested.

Feature windows: 1h / 6h / 24h / 7d:
    counts, net sentiment (mean), topic intensity (per-topic counts),
    surprise index (z-score of current 24h count vs trailing 7d baseline).

VALUE TEST (honesty-critical):
    Compare the same forecasting model WITH vs WITHOUT news features under
    identical walk-forward splits; Diebold-Mariano on paired loss
    differences. Verdict strings state exactly what happened — if news does
    not help, the report says so and news stays contextual-only.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

WINDOWS_H = {"1h": 1, "6h": 6, "24h": 24, "168h": 168}


def _parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def news_features(
    items: Sequence[dict], as_of: datetime, window_key: str = "24h"
) -> dict[str, object]:
    """Aggregate news features strictly as-of ``as_of`` (past window only)."""
    hours = WINDOWS_H[window_key]
    start = as_of - timedelta(hours=hours)
    visible = []
    for it in items:
        avail = _parse(it["available_at"])
        if start < avail <= as_of:  # point-in-time: never the future
            visible.append(it)
    n = len(visible)
    senti = [float(it.get("sentiment") or 0.0) for it in visible]
    topics: dict[str, int] = {}
    for it in visible:
        for t in it.get("topics") or []:
            topics[t] = topics.get(t, 0) + 1
    return {
        "window": window_key,
        "count": n,
        "net_sentiment": round(sum(senti) / n, 4) if n else 0.0,
        "topic_counts": topics,
        "items_used": n,
    }


def surprise_index(items: Sequence[dict], as_of: datetime) -> float:
    """z-score of trailing-24h news count vs trailing-7d daily mean."""
    past = [it for it in items if _parse(it["available_at"]) <= as_of]
    if not past:
        return 0.0
    last24 = sum(
        1 for it in past if as_of - timedelta(hours=24) < _parse(it["available_at"]) <= as_of
    )
    week = [
        it
        for it in past
        if as_of - timedelta(hours=168) < _parse(it["available_at"]) <= as_of - timedelta(hours=24)
    ]
    daily = len(week) / 6.0
    if daily <= 0:
        return float(last24)  # no baseline yet — raw count, honestly
    return round((last24 - daily) / math.sqrt(daily + 1e-9), 4)


# ------------------------------------------------------------------ value ----
@dataclass
class NewsValueVerdict:
    instrument: str
    horizon: int
    dm_stat: float | None
    p_value: float | None
    mae_with: float
    mae_without: float
    n_observations: int
    verdict: str
    notes: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def verdict_from_dm(dm_stat: float | None, p_value: float | None, alpha: float = 0.05) -> str:
    """Honest verdict strings — news value is reported, not assumed."""
    if dm_stat is None or p_value is None:
        return "insufficient evidence (fewer paired observations than required)"
    if p_value < alpha and dm_stat < 0:
        return "news features improve forecasts significantly (DM, paired loss)"
    if p_value < alpha and dm_stat > 0:
        return "news features make forecasts significantly WORSE (DM, paired loss)"
    return "no significant difference — news kept as context only"


def diebold_mariano(
    loss_a: Sequence[float], loss_b: Sequence[float]
) -> tuple[float | None, float | None]:
    """DM statistic for paired loss differentials (two-sided normal p-value).

    Positive d = model A worse than B. Uses scipy when available; a pure
    normal-approx fallback keeps the function dependency-light.
    """
    if len(loss_a) != len(loss_b) or len(loss_a) < 8:
        return None, None
    d = [a - b for a, b in zip(loss_a, loss_b, strict=False)]
    n = len(d)
    mean = sum(d) / n
    var = sum((x - mean) ** 2 for x in d) / n
    if var <= 0:
        if mean == 0:
            return 0.0, 1.0
        # constant nonzero differential: degenerate but decisive
        stat = mean / math.sqrt(1e-12 / n)
    else:
        stat = mean / math.sqrt(var / n)
    try:
        from scipy import stats

        p = float(2 * (1 - stats.norm.cdf(abs(stat))))
    except Exception:
        p = float(math.erfc(abs(stat) / math.sqrt(2)))
    return float(stat), p


def news_value_test(
    losses_with: Sequence[float],
    losses_without: Sequence[float],
    instrument: str,
    horizon: int,
) -> NewsValueVerdict:
    stat, p = diebold_mariano(losses_with, losses_without)
    n = len(losses_with)
    mae_w = sum(losses_with) / n if n else float("nan")
    mae_wo = sum(losses_without) / n if n else float("nan")
    return NewsValueVerdict(
        instrument=instrument,
        horizon=horizon,
        dm_stat=stat,
        p_value=p,
        mae_with=round(mae_w, 6),
        mae_without=round(mae_wo, 6),
        n_observations=n,
        verdict=verdict_from_dm(stat, p),
    )
