"""Market trend analysis: direction, strength, slope, volatility regime."""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from app.services.features.indicators import atr, ema, log_returns, rolling_volatility, rsi, sma

# Slope (log-price per day) magnitude below this counts as "sideways".
SIDEWAYS_SLOPE_THRESHOLD = 2e-4


def analyze_trend(df: pd.DataFrame, lookback: int = 30) -> Dict:
    """Analyse the trend of an OHLC frame using the last ``lookback`` bars.

    Returns a JSON-safe dict with direction, strength (0-100), slope,
    volatility regime and a set of key indicator values.
    """
    if len(df) < 5:
        raise ValueError("Need at least 5 bars for trend analysis")
    df = df.sort_values("timestamp").reset_index(drop=True)
    close = df["close"].astype(float)
    n = min(lookback, len(close))
    window = close.iloc[-n:]
    x = np.arange(n, dtype=float)
    log_window = np.log(window.to_numpy())

    slope, intercept = np.polyfit(x, log_window, 1)
    fitted = slope * x + intercept
    resid = log_window - fitted
    ss_tot = float(np.sum((log_window - log_window.mean()) ** 2))
    ss_res = float(np.sum(resid ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    if slope > SIDEWAYS_SLOPE_THRESHOLD:
        direction = "up"
    elif slope < -SIDEWAYS_SLOPE_THRESHOLD:
        direction = "down"
    else:
        direction = "sideways"

    # Strength: how much of the window's variation is explained by the trend,
    # scaled by the size of the slope relative to its threshold.
    slope_score = min(1.0, abs(slope) / (4 * SIDEWAYS_SLOPE_THRESHOLD))
    strength = float(round(100.0 * max(0.0, r_squared) * slope_score, 1))

    rets = log_returns(close)
    vol_20 = float(rolling_volatility(rets, min(20, len(rets))).iloc[-1]) if len(rets) >= 2 else float("nan")
    vol_hist = rolling_volatility(rets, min(60, len(rets))).dropna()
    if not vol_hist.empty and vol_20 == vol_20:  # not NaN
        percentile = float((vol_hist < vol_20).mean())
    else:
        percentile = 0.5
    if percentile < 0.34:
        vol_regime = "low"
    elif percentile < 0.67:
        vol_regime = "medium"
    else:
        vol_regime = "high"

    rsi_series = rsi(close)
    macd_line = ema(close, 12) - ema(close, 26)
    atr_series = atr(df["high"], df["low"], close, 14)
    sma20 = sma(close, 20)
    sma50 = sma(close, 50)

    indicators = {
        "rsi_14": _round(rsi_series.iloc[-1], 2),
        "macd": _round(macd_line.iloc[-1], 6),
        "sma_20": _round(sma20.iloc[-1], 6),
        "sma_50": _round(sma50.iloc[-1], 6),
        "atr_14": _round(atr_series.iloc[-1], 6),
        "vol_20d_annualized": _round(vol_20 * np.sqrt(252.0) * 100.0, 2),
        "close": _round(float(close.iloc[-1]), 6),
    }

    return {
        "direction": direction,
        "strength": strength,
        "slope_per_day": _round(slope, 8),
        "r_squared": _round(r_squared, 4),
        "lookback_bars": n,
        "volatility_regime": vol_regime,
        "volatility_percentile": _round(percentile * 100.0, 1),
        "indicators": indicators,
    }


def _round(value: float, ndigits: int) -> float | None:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return None
    return round(float(value), ndigits)
