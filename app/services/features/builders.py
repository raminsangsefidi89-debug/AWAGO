"""Feature builders: pure pandas, trailing windows only (point-in-time safe).

Every function maps a bar frame (timestamp, open, high, low, close) to
columns that at row T depend only on rows <= T. The leakage harness
(perturb-future audit) mechanically enforces this in tests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.features.set import CORE_FEATURE_SET


def _log_returns(close: pd.Series, horizon: int) -> pd.Series:
    return np.log(close / close.shift(horizon))


def _rolling_std(ret: pd.Series, window: int) -> pd.Series:
    return ret.rolling(window, min_periods=window).std()


def build_core_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the core single-pair feature block from OHLC bars.

    ``df`` must contain (timestamp, open, high, low, close) sorted by
    timestamp. Returns a frame on the same timestamps with the registered
    core columns (cross-pair block excluded).
    """
    out = pd.DataFrame({"timestamp": pd.to_datetime(df["timestamp"]).reset_index(drop=True)})
    open_ = pd.to_numeric(df["open"]).reset_index(drop=True).astype(float)
    high = pd.to_numeric(df["high"]).reset_index(drop=True).astype(float)
    low = pd.to_numeric(df["low"]).reset_index(drop=True).astype(float)
    close = pd.to_numeric(df["close"]).reset_index(drop=True).astype(float)

    log_close = np.log(close)

    # --- returns ---
    out["ret_1d"] = _log_returns(close, 1)
    out["ret_5d"] = _log_returns(close, 5)
    out["ret_10d"] = _log_returns(close, 10)
    out["ret_20d"] = _log_returns(close, 20)

    # --- volatility estimators ---
    ret1 = out["ret_1d"]
    out["vol_cc_20"] = _rolling_std(ret1, 20)
    log_hl = np.log(high / low)
    out["vol_parkinson_20"] = np.sqrt(
        (log_hl**2).rolling(20, min_periods=20).mean() / (4.0 * np.log(2.0))
    )
    log_co = np.log(close / open_)
    gk = 0.5 * log_hl**2 - (2.0 * np.log(2.0) - 1.0) * log_co**2
    out["vol_gk_20"] = np.sqrt(gk.rolling(20, min_periods=20).mean())

    # --- momentum ---
    out["mom_10"] = _log_returns(close, 10)
    out["mom_20"] = _log_returns(close, 20)
    out["mom_60"] = _log_returns(close, 60)

    # --- mean reversion z-scores ---
    for window, name in ((20, "zscore_20"), (60, "zscore_60")):
        ma = close.rolling(window, min_periods=window).mean()
        sd = close.rolling(window, min_periods=window).std()
        out[name] = (close - ma) / sd.replace(0.0, np.nan)

    # --- RSI(14) ---
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0.0, 100.0)
    out["rsi_14"] = rsi

    # --- MACD histogram (12,26,9) ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    out["macd_hist"] = macd - signal

    # --- Bollinger %B and bandwidth (20, 2σ) ---
    ma20 = close.rolling(20, min_periods=20).mean()
    sd20 = close.rolling(20, min_periods=20).std()
    upper = ma20 + 2.0 * sd20
    lower = ma20 - 2.0 * sd20
    out["bb_pct_b_20"] = (close - lower) / (upper - lower).replace(0.0, np.nan)
    out["bb_width_20"] = (upper - lower) / ma20.replace(0.0, np.nan)

    # --- ATR(14) ---
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    out["atr_14"] = true_range.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()

    # --- rolling distribution shape ---
    out["skew_20"] = ret1.rolling(20, min_periods=20).skew()
    out["kurt_20"] = ret1.rolling(20, min_periods=20).kurt()

    # --- OLS slopes of log price ---
    for window, name in ((10, "slope_10"), (20, "slope_20")):
        out[name] = log_close.rolling(window, min_periods=window).apply(
            lambda y: np.polyfit(np.arange(len(y)), y, 1)[0], raw=True
        )

    # --- drawdown from 60d rolling max ---
    rolling_max = close.rolling(60, min_periods=60).max()
    out["drawdown_60"] = close / rolling_max - 1.0

    # --- calendar (uses only the row's own timestamp) ---
    ts = pd.to_datetime(out["timestamp"])
    dow = ts.dt.dayofweek.to_numpy()
    month = ts.dt.month.to_numpy()
    out["dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    out["dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)
    out["month_sin"] = np.sin(2.0 * np.pi * month / 12.0)
    out["month_cos"] = np.cos(2.0 * np.pi * month / 12.0)

    return out


def build_cross_pair_features(
    primary: pd.DataFrame,
    other_frames: dict[str, pd.DataFrame],
    usd_pairs: list[str] | None = None,
) -> pd.DataFrame:
    """Cross-pair block: USD basket factor, relative strength, rolling corr.

    All series are merged on timestamp with an inner join and shifted so a
    row at T only ever sees rows <= T of every input. Missing inputs yield
    all-NaN columns (never silently filled from the future).
    """
    out = pd.DataFrame({"timestamp": pd.to_datetime(primary["timestamp"]).reset_index(drop=True)})
    usd_pairs = usd_pairs or [
        "EUR/USD",
        "GBP/USD",
        "AUD/USD",
        "NZD/USD",
        "USD/JPY",
        "USD/CHF",
        "USD/CAD",
        "USD/TRY",
    ]

    def _closes(df: pd.DataFrame) -> pd.Series:
        s = pd.Series(pd.to_numeric(df["close"]).to_numpy(), index=pd.to_datetime(df["timestamp"]))
        return s[~s.index.duplicated(keep="last")].sort_index()

    primary_close = _closes(primary)
    legs = {}
    for symbol in usd_pairs:
        if symbol in other_frames and len(other_frames[symbol]) > 0:
            legs[symbol] = _closes(other_frames[symbol])
        elif symbol == primary.get("pair_symbol", ()):  # primary itself can serve as a leg
            legs[symbol] = primary_close

    # USD basket: average 20d log return of every available USD leg.
    if legs:
        rets = []
        for symbol, series in legs.items():
            r = np.log(series / series.shift(20))
            # USD-side pairs need sign flip (USD is the base currency there)
            if symbol.startswith("USD/"):
                r = -r
            rets.append(r.rename(symbol))
        basket = pd.concat(rets, axis=1, join="inner").mean(axis=1)
    else:
        basket = pd.Series(dtype=float)

    if len(basket) > 0:
        aligned = basket.reindex(pd.to_datetime(out["timestamp"])).to_numpy()
        out["usd_factor_20"] = aligned
    else:
        out["usd_factor_20"] = np.nan

    if len(basket) > 0:
        prim_ret20 = np.log(primary_close / primary_close.shift(20))
        prim_aligned = prim_ret20.reindex(pd.to_datetime(out["timestamp"])).to_numpy()
        out["rel_strength_20"] = prim_aligned - out["usd_factor_20"]
        prim_ret1 = np.log(primary_close / primary_close.shift(1))
        basket_ret1 = basket.diff()
        joined = pd.DataFrame({"p": prim_ret1, "b": basket_ret1}).dropna()
        corr = joined["p"].rolling(20, min_periods=20).corr(joined["b"])
        out["corr_usd_20"] = corr.reindex(pd.to_datetime(out["timestamp"])).to_numpy()
    else:
        out["rel_strength_20"] = np.nan
        out["corr_usd_20"] = np.nan

    return out


def build_feature_frame(
    primary: pd.DataFrame,
    other_frames: dict[str, pd.DataFrame] | None = None,
    pair_symbol: str = "",
) -> pd.DataFrame:
    """Full feature frame: core + cross-pair blocks, point-in-time safe.

    The frame carries no target columns by design (targets are appended only
    by the modeling layer, so feature frames can never leak a target).
    """
    core = build_core_features(primary)
    cross = build_cross_pair_features(primary, other_frames or {})
    frame = core.merge(cross, on="timestamp", how="left")

    # Order columns exactly as the registry declares, then assert parity.
    expected = CORE_FEATURE_SET.feature_names
    missing = [c for c in expected if c not in frame.columns]
    if missing:
        raise AssertionError(f"Feature builders missing columns: {missing}")
    frame = frame[["timestamp", *expected]]
    frame.insert(0, "pair_symbol", pair_symbol)
    return frame
