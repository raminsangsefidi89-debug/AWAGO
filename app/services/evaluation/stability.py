"""Stability analysis: performance broken down by year, regime, and pair.

Honesty: subgroup results are descriptive, not selection criteria — looking
at them and then picking the winner for the good subgroup is exactly the
cherry-picking the project forbids. The breakdown exists to *surface*
failures (e.g., "model only works in low-vol years").
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.evaluation.metrics import directional_accuracy, mae


def _regime_labels(timestamps: pd.Series, close: pd.Series, window: int = 20) -> pd.Series:
    """Volatility regime by tercile of trailing realized vol (past-only)."""
    rets = np.log(close / close.shift(1))
    vol = rets.rolling(window, min_periods=window).std()
    # expanding terciles: cut points computed from data up to each row? For
    # simplicity and honesty we use a FIXED split at the full-sample terciles
    # but label it as descriptive (not a model input).
    q1, q2 = vol.quantile([1 / 3, 2 / 3])
    labels = pd.Series("mid", index=vol.index)
    labels[vol <= q1] = "low_vol"
    labels[vol > q2] = "high_vol"
    return labels.fillna("mid")


def stability_report(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    timestamps: pd.DatetimeIndex | pd.Series,
    close: pd.Series,
    pair_symbol: str = "",
    model_name: str = "",
) -> dict[str, Any]:
    ts = pd.Series(pd.to_datetime(timestamps)).reset_index(drop=True)
    y = np.asarray(y_true, dtype=float)
    yhat = np.asarray(y_pred, dtype=float)
    close = pd.Series(np.asarray(close, dtype=float)).reset_index(drop=True)
    n = min(len(ts), len(y))
    ts, y, yhat, close = ts.iloc[:n], y[:n], yhat[:n], close.iloc[:n]

    regimes = _regime_labels(ts, close)
    years = ts.dt.year

    def _block(mask: pd.Series) -> dict[str, Any]:
        if int(mask.sum()) < 5:
            return {"n": int(mask.sum()), "note": "too few rows"}
        yy, pp = y[mask.to_numpy()], yhat[mask.to_numpy()]
        return {
            "n": int(mask.sum()),
            "mae": round(mae(yy, pp), 8),
            "directional_accuracy": round(directional_accuracy(yy, pp), 4),
        }

    by_year = {str(year): _block(years == year) for year in sorted(years.unique())}
    by_regime = {regime: _block(regimes == regime) for regime in ("low_vol", "mid", "high_vol")}

    return {
        "pair_symbol": pair_symbol,
        "model_name": model_name,
        "by_year": by_year,
        "by_vol_regime": by_regime,
        "caveat": (
            "Subgroup tables are descriptive failure-surfacing, not selection "
            "criteria; choosing a model because of its best subgroup would be "
            "cherry-picking."
        ),
    }
