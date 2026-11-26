"""Forecast evaluation metrics + statistical comparison tests."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def mae(y: np.ndarray, yhat: np.ndarray) -> float:
    return float(np.mean(np.abs(y - yhat)))


def rmse(y: np.ndarray, yhat: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - yhat) ** 2)))


def mase(y: np.ndarray, yhat: np.ndarray, insample: np.ndarray, season: int = 1) -> float:
    """Mean absolute scaled error; scale = in-sample naive MAE."""
    if len(insample) <= season:
        return float("nan")
    scale = float(np.mean(np.abs(insample[season:] - insample[:-season])))
    if scale == 0:
        return float("nan")
    return float(np.mean(np.abs(y - yhat)) / scale)


def smape(y: np.ndarray, yhat: np.ndarray) -> float:
    denom = np.abs(y) + np.abs(yhat)
    mask = denom > 0
    if not mask.any():
        return float("nan")
    return float(np.mean(2.0 * np.abs(y[mask] - yhat[mask]) / denom[mask]))


def directional_accuracy(y: np.ndarray, yhat: np.ndarray) -> float:
    """Sign agreement of predicted vs realized returns."""
    if len(y) == 0:
        return float("nan")
    return float(np.mean(np.sign(y) == np.sign(yhat)))


def pinball_loss(y: np.ndarray, q_pred: np.ndarray, q: float) -> float:
    diff = y - q_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def crps_from_quantiles(y: np.ndarray, quantile_preds: dict[float, np.ndarray]) -> float:
    """Approximate CRPS by integrating pinball losses over the quantile grid."""
    if not quantile_preds:
        return float("nan")
    qs = sorted(quantile_preds)
    losses = [2.0 * pinball_loss(y, quantile_preds[q], q) for q in qs]
    return float(np.mean(losses))


def winkler_score(
    y: np.ndarray, lower: np.ndarray, upper: np.ndarray, level: float = 0.90
) -> float:
    """Winkler (interval) score — lower is better; penalizes misses by width/alpha."""
    alpha = 1.0 - level
    width = upper - lower
    score = width.copy()
    score = score + (2.0 / alpha) * np.maximum(lower - y, 0.0)
    score = score + (2.0 / alpha) * np.maximum(y - upper, 0.0)
    return float(np.mean(score))


def coverage(y: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    return float(np.mean((y >= lower) & (y <= upper)))


def diebold_mariano(
    err_a: np.ndarray,
    err_b: np.ndarray,
    h: int = 1,
    loss: str = "abs",
) -> dict[str, float]:
    """Diebold-Mariano test with Harvey-Leybourne-Newbold correction.

    H0: equal predictive accuracy. ``err_*`` are forecast errors of models A
    and B on the SAME rows (the runner guarantees this).
    """
    a = np.asarray(err_a, dtype=float)
    b = np.asarray(err_b, dtype=float)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    if loss == "abs":
        la, lb = np.abs(a), np.abs(b)
    else:
        la, lb = a**2, b**2
    d = la - lb
    mean_d = float(d.mean())
    if n < 3:
        return {"dm_stat": float("nan"), "p_value": float("nan"), "mean_loss_diff": mean_d, "n": n}
    gamma0 = float(np.var(d, ddof=1))
    # autocorrelation-robust variance up to lag h-1
    var = gamma0
    for lag in range(1, max(1, h)):
        if lag >= n:
            break
        cov = float(np.cov(d[lag:], d[:-lag], ddof=0)[0, 1])
        var += 2.0 * (1.0 - lag / h) * cov
    var = max(var, 1e-12)
    dm = mean_d / np.sqrt(var / n)
    # Harvey correction + small-sample t
    from scipy import stats

    adj = dm * np.sqrt((1.0 - (1.0 / n)) * (n + 1 - 2 * h + (h * (h - 1)) / n) / n)
    p = float(2.0 * stats.t.sf(np.abs(adj), df=n - 1))
    return {"dm_stat": float(adj), "p_value": p, "mean_loss_diff": mean_d, "n": int(n)}


def holm_bonferroni(p_values: Sequence[tuple[str, float]]) -> dict[str, float]:
    """Holm step-down adjusted p-values (multiple-comparison control)."""
    m = len(p_values)
    ordered = sorted(p_values, key=lambda kv: kv[1])
    adjusted: dict[str, float] = {}
    running_max = 0.0
    for i, (name, p) in enumerate(ordered):
        adj = min(1.0, (m - i) * p)
        running_max = max(running_max, adj)
        adjusted[name] = round(running_max, 6)
    return adjusted


def verdict_vs_baseline(
    mae_model: float,
    mae_baseline: float,
    dm_result: dict[str, float] | None,
    alpha: float = 0.05,
) -> str:
    """Honest verdict text used verbatim in leaderboards and UI."""
    if mae_model < mae_baseline:
        if (
            dm_result
            and dm_result.get("p_value", 1.0) < alpha
            and dm_result.get("mean_loss_diff", 0.0) < 0
        ):
            return "beats baseline significantly"
        return "beats baseline, not significantly"
    if (
        dm_result
        and dm_result.get("p_value", 1.0) < alpha
        and dm_result.get("mean_loss_diff", 0.0) > 0
    ):
        return "worse than baseline (significant)"
    return "not better than baseline"


def full_metric_suite(
    y: np.ndarray,
    yhat: np.ndarray,
    insample: np.ndarray,
    quantile_preds: dict[float, np.ndarray] | None = None,
    level: float = 0.90,
) -> dict[str, float]:
    out = {
        "mae": mae(y, yhat),
        "rmse": rmse(y, yhat),
        "mase": mase(y, yhat, insample),
        "smape": smape(y, yhat),
        "directional_accuracy": directional_accuracy(y, yhat),
    }
    if quantile_preds:

        def _get(q: float):
            for key, val in quantile_preds.items():
                if abs(key - q) < 1e-6:
                    return val
            return None

        p10 = _get(0.1)
        p90 = _get(0.9)
        out["crps"] = crps_from_quantiles(y, quantile_preds)
        out["pinball_10"] = pinball_loss(y, yhat if p10 is None else p10, 0.1)
        out["pinball_90"] = pinball_loss(y, yhat if p90 is None else p90, 0.9)
        lo = _get((1.0 - level) / 2.0)
        hi = _get(1.0 - (1.0 - level) / 2.0)
        if lo is not None and hi is not None:
            out["coverage"] = coverage(y, lo, hi)
            out["interval_width"] = float(np.mean(hi - lo))
            out["winkler"] = winkler_score(y, lo, hi, level)
    return out
