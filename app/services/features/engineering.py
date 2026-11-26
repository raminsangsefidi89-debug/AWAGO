"""Leak-free feature engineering for forecasting.

Design rules (enforced by tests):
  * Features at row t use only data from rows <= t.
  * Targets are strictly in the future: target(t) = f(close_{t+h}).
  * No scaler/transformer is fit here; models fit them on training folds only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.features.indicators import compute_indicator_frame

# Bump when the feature set changes; persisted with every model artifact.
FEATURES_VERSION = "2"

CALENDAR_COLUMNS = ["dow", "month", "dom", "dow_sin", "dow_cos", "month_sin", "month_cos"]


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calendar features of the bar's own timestamp (known at time t)."""
    ts = df["timestamp"]
    out = pd.DataFrame(index=df.index)
    # pandas renamed `dayofweek` -> `day_of_week`; support both.
    day_of_week = getattr(ts.dt, "day_of_week", None)
    if day_of_week is None:
        day_of_week = ts.dt.dayofweek
    out["dow"] = day_of_week.astype(float)
    out["month"] = ts.dt.month.astype(float)
    out["dom"] = ts.dt.day.astype(float)
    out["dow_sin"] = np.sin(2 * np.pi * out["dow"] / 7.0)
    out["dow_cos"] = np.cos(2 * np.pi * out["dow"] / 7.0)
    out["month_sin"] = np.sin(2 * np.pi * out["month"] / 12.0)
    out["month_cos"] = np.cos(2 * np.pi * out["month"] / 12.0)
    return out


def target_log_return(close: pd.Series, horizon: int) -> pd.Series:
    """Future log return over ``horizon`` days: ln(close_{t+h} / close_t)."""
    return np.log(close.shift(-horizon) / close)


def target_future_close(close: pd.Series, horizon: int) -> pd.Series:
    """Future close price at t+h."""
    return close.shift(-horizon)


def build_feature_frame(df: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Build the complete modelling frame from raw OHLC bars.

    Parameters
    ----------
    df : chronological frame with columns timestamp, open, high, low, close.
    horizons : target horizons (trading days) to generate targets for.

    Returns
    -------
    DataFrame with: timestamp, close, one column per feature, and for each
    horizon ``h``: ``target_logret_h{h}`` and ``target_close_h{h}``.
    Rows keep NaN targets at the end of the series (used for inference).
    """
    df = df.sort_values("timestamp").reset_index(drop=True).copy()
    base = pd.DataFrame(
        {"timestamp": pd.to_datetime(df["timestamp"], utc=True), "close": df["close"].astype(float)}
    )

    indicators = compute_indicator_frame(df)
    calendar = add_calendar_features(base)

    out = pd.concat([base, indicators, calendar], axis=1)
    for h in horizons:
        out[f"target_logret_h{h}"] = target_log_return(out["close"], h)
        out[f"target_close_h{h}"] = target_future_close(out["close"], h)
    return out


def feature_columns(horizons: list[int] | None = None) -> list[str]:
    """Names of the model input features (no targets, no identifiers)."""
    from app.services.features.indicators import compute_indicator_frame  # local import for clarity

    # Derive the indicator names from the indicator module's own output shape.
    sample = pd.DataFrame(
        {
            "open": [1.0, 1.0, 1.0],
            "high": [1.0, 1.0, 1.0],
            "low": [1.0, 1.0, 1.0],
            "close": [1.0, 1.0, 1.0],
        }
    )
    indicator_names = [c for c in compute_indicator_frame(sample).columns]
    # lag-return columns are part of the indicator frame already
    return indicator_names + CALENDAR_COLUMNS
