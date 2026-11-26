"""Volatility regimes and change-points (P1 overlays).

Two simple, auditable detectors:

* **Volatility regime**: trailing realized vol vs its own expanding terciles
  -> low / mid / high. Point-in-time (each label uses only past vol).
* **CUSUM change-point detector** on log returns: flags persistent mean
  shifts. Cheap, deterministic, no new dependencies.

Usage: regime labels are FEATURES/OVERLAYS only (never retroactively applied
to explain results after the fact — that would be hindsight storytelling).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def vol_regime(close: pd.Series, window: int = 20) -> pd.Series:
    """Trailing-vol regime label per row (point-in-time)."""
    rets = np.log(close / close.shift(1))
    vol = rets.rolling(window, min_periods=window).std()
    labels = []
    for i in range(len(vol)):
        v = vol.iloc[: i + 1].dropna()
        if len(v) < window:
            labels.append("unknown")
            continue
        q1, q2 = v.quantile([1 / 3, 2 / 3])
        cur = vol.iloc[i]
        labels.append("low_vol" if cur <= q1 else ("high_vol" if cur > q2 else "mid"))
    return pd.Series(labels, index=close.index, name="vol_regime")


def cusum_change_points(
    returns: pd.Series,
    threshold: float = 4.0,
    drift: float = 0.5,
) -> list[int]:
    """Classic CUSUM: returns indices where the cumulative sum crosses."""
    x = (returns.fillna(0.0) - returns.mean()).to_numpy()
    s_pos = np.zeros(len(x))
    s_neg = np.zeros(len(x))
    points: list[int] = []
    for i in range(1, len(x)):
        s_pos[i] = max(0.0, s_pos[i - 1] + x[i] - drift * returns.std())
        s_neg[i] = max(0.0, s_neg[i - 1] - x[i] - drift * returns.std())
        if s_pos[i] > threshold * returns.std() or s_neg[i] > threshold * returns.std():
            points.append(i)
            s_pos[i] = 0.0
            s_neg[i] = 0.0
    return points


def regime_summary(close: pd.Series) -> dict[str, int]:
    labels = vol_regime(close)
    return {str(k): int(v) for k, v in labels.value_counts().items()}
