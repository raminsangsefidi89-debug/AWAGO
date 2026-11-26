"""Technical indicators computed with backward-looking windows only.

Every function here uses information available at time t (or earlier) to
produce the value at t. NaN is returned where the window is not yet full.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    """Simple moving average over the trailing ``window`` observations."""
    return close.rolling(window=window, min_periods=window).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    """Exponential moving average (pandas ewm, adjust=False, backward only)."""
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def log_returns(close: pd.Series) -> pd.Series:
    """One-day log returns: ln(close_t / close_{t-1})."""
    return np.log(close / close.shift(1))


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder smoothing)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # Edge cases when avg_loss is exactly zero:
    out = out.mask((avg_loss == 0) & (avg_gain > 0), 100.0)  # only gains -> RSI 100
    out = out.mask((avg_loss == 0) & (avg_gain == 0), 50.0)  # flat -> neutral
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD line, signal line and histogram."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame(
        {"macd": macd_line, "macd_signal": signal_line, "macd_hist": macd_line - signal_line},
        index=close.index,
    )


def bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands: middle SMA, upper/lower bands, width and %B."""
    mid = close.rolling(window=window, min_periods=window).mean()
    std = close.rolling(window=window, min_periods=window).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower) / mid
    pct_b = (close - lower) / (upper - lower)
    return pd.DataFrame(
        {"bb_mid": mid, "bb_upper": upper, "bb_lower": lower, "bb_width": width, "bb_pct_b": pct_b},
        index=close.index,
    )


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range (Wilder).

    When a source is close-only (high == low == close, e.g. Frankfurter),
    the true range degenerates to the close-to-close range, which is a
    sensible volatility proxy.
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def rolling_volatility(log_ret: pd.Series, window: int) -> pd.Series:
    """Rolling standard deviation of log returns (annualization left to callers)."""
    return log_ret.rolling(window=window, min_periods=window).std(ddof=1)


def historical_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    """Rolling annualized volatility of log returns (252 trading days)."""
    return rolling_volatility(log_returns(close), window) * np.sqrt(252.0)


def compute_indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the full indicator set for an OHLC frame.

    ``df`` must be sorted chronologically with columns:
    open, high, low, close. Returns a DataFrame of indicator columns only.
    """
    close = df["close"]
    out = pd.DataFrame(index=df.index)

    out["log_ret_1d"] = log_returns(close)
    for lag in (2, 3, 5, 10):
        out[f"log_ret_lag_{lag}"] = out["log_ret_1d"].shift(lag - 1)

    for w in (5, 10, 20, 50):
        out[f"sma_{w}"] = sma(close, w)
        out[f"dist_sma_{w}"] = close / out[f"sma_{w}"] - 1.0

    out["ema_12"] = ema(close, 12)
    out["ema_26"] = ema(close, 26)
    out["rsi_14"] = rsi(close, 14)

    macd_df = macd(close)
    out = out.join(macd_df)

    bb_df = bollinger(close)
    out = out.join(bb_df)

    out["atr_14"] = atr(df["high"], df["low"], close, 14)
    out["vol_5d"] = rolling_volatility(out["log_ret_1d"], 5)
    out["vol_20d"] = rolling_volatility(out["log_ret_1d"], 20)
    out["vol_60d"] = rolling_volatility(out["log_ret_1d"], 60)
    out["vol_ratio_5_20"] = out["vol_5d"] / out["vol_20d"]

    return out
