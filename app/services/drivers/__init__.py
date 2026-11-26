"""Drivers layer (addendum D): rolling relations, lead-lag, regime dependence,
permutation importance. Spurious-correlation cautions are first-class output.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

SPURIOUS_CAUTION = (
    "Correlation is not causation — rolling correlations between trending "
    "series can be spurious. Lead-lag hints are exploratory only."
)


def _pearson(x: Sequence[float], y: Sequence[float]) -> float:
    n = min(len(x), len(y))
    if n < 3:
        return float("nan")
    xs, ys = list(x[-n:]), list(y[-n:])
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys, strict=False))
    vx = sum((a - mx) ** 2 for a in xs)
    vy = sum((b - my) ** 2 for b in ys)
    if vx <= 0 or vy <= 0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


def rolling_correlation(
    a: Sequence[float], b: Sequence[float], window: int = 60
) -> list[tuple[int, float]]:
    """(end_index, corr) over a trailing window. Causality not implied."""
    out: list[tuple[int, float]] = []
    for end in range(window, min(len(a), len(b)) + 1):
        out.append((end, round(_pearson(a[end - window : end], b[end - window : end]), 4)))
    return out


def lead_lag(a: Sequence[float], b: Sequence[float], max_lag: int = 5) -> dict[str, object]:
    """Best lag of a leading b by cross-correlation of first differences."""
    da = [a[i] - a[i - 1] for i in range(1, len(a))]
    db = [b[i] - b[i - 1] for i in range(1, len(b))]
    n = min(len(da), len(db))
    da, db = da[-n:], db[-n:]
    scores = {}
    best_lag, best_corr = 0, 0.0
    for lag in range(0, max_lag + 1):
        if lag == 0:
            c = _pearson(da, db)
        else:
            c = _pearson(da[:-lag], db[lag:])
        scores[lag] = None if (isinstance(c, float) and math.isnan(c)) else round(c, 4)
        if scores[lag] is not None and abs(c) > abs(best_corr):
            best_lag, best_corr = lag, c
    return {
        "best_lag": best_lag,
        "best_corr": round(best_corr, 4),
        "by_lag": scores,
        "caution": SPURIOUS_CAUTION,
    }


def regime_dependence(
    x: Sequence[float], y: Sequence[float], regime_flags: Sequence[str]
) -> dict[str, float]:
    """Correlation per regime label (e.g. high/low vol). Needs >= 3 points each."""
    buckets: dict[str, tuple[list[float], list[float]]] = {}
    for xi, yi, r in zip(x, y, regime_flags, strict=False):
        bx, by = buckets.setdefault(r, ([], []))
        bx.append(xi)
        by.append(yi)
    return {
        r: (round(_pearson(bx, by), 4) if len(bx) >= 3 else float("nan"))
        for r, (bx, by) in sorted(buckets.items())
    }


@dataclass
class ImportanceResult:
    feature: str
    importance: float  # baseline_mae - permuted_mae (higher = more useful)


def permutation_importance(
    model_predict,  # callable(X) -> yhat
    X: Sequence[Sequence[float]],
    y: Sequence[float],
    feature_names: Sequence[str],
    mae_fn=None,
    seed: int = 42,
) -> list[ImportanceResult]:
    """Model-agnostic permutation importance on MAE. Deterministic given seed."""
    import random

    rng = random.Random(seed)
    mae = mae_fn or (
        lambda yh, yy: sum(abs(a - b) for a, b in zip(yh, yy, strict=False)) / max(1, len(yy))
    )
    base = mae(model_predict(X), y)
    rows = [list(r) for r in X]
    results: list[ImportanceResult] = []
    for j, name in enumerate(feature_names):
        permuted = [list(r) for r in rows]
        col = [r[j] for r in permuted]
        rng.shuffle(col)
        for i, r in enumerate(permuted):
            r[j] = col[i]
        perm_mae = mae(model_predict(permuted), y)
        results.append(ImportanceResult(name, round(base - perm_mae, 6)))
    return sorted(results, key=lambda r: -abs(r.importance))
