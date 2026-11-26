"""Simple, honest forecasting baselines every model is compared against."""

from __future__ import annotations

import numpy as np
import pandas as pd


def naive_forecast(last_close: float, horizon: int) -> float:
    """Naive baseline: the price h days ahead equals today's price."""
    _ = horizon
    return float(last_close)


def drift_forecast(close: pd.Series, horizon: int, window: int = 20) -> float:
    """Drift baseline: continue the mean log return of the last ``window`` days."""
    last_close = float(close.iloc[-1])
    rets = np.log(close / close.shift(1)).dropna().iloc[-window:]
    if rets.empty:
        return last_close
    mean_ret = float(rets.mean())
    return float(last_close * np.exp(mean_ret * horizon))


def baseline_predictions(
    close: pd.Series,
    horizons: list[int],
) -> dict[str, dict[int, np.ndarray]]:
    """Vectorised baseline predictions for each horizon over the full series.

    For row t (predicting close_{t+h}): naive predicts close_t;
    drift predicts close_t * exp(mean_ret_window(t) * h).
    """
    close = close.astype(float)
    log_ret = np.log(close / close.shift(1))
    out: dict[str, dict[int, np.ndarray]] = {"naive": {}, "drift": {}}
    for h in horizons:
        naive = close.to_numpy()  # prediction at t is close_t
        window_means = log_ret.rolling(20, min_periods=5).mean().to_numpy()
        drift = close.to_numpy() * np.exp(np.nan_to_num(window_means) * h)
        out["naive"][h] = naive
        out["drift"][h] = drift
    return out
