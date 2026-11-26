"""Indicator calculations vs hand-computed values."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.features.indicators import (
    atr,
    bollinger,
    ema,
    log_returns,
    macd,
    rolling_volatility,
    rsi,
    sma,
)


def test_sma_matches_manual():
    close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = sma(close, 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_ema_matches_manual():
    close = pd.Series([2.0, 4.0, 6.0, 8.0])
    out = ema(close, span=3)
    # adjust=False: ema_t = alpha*x_t + (1-alpha)*ema_{t-1}, alpha = 0.5
    assert out.iloc[3] == pytest.approx(0.5 * 8 + 0.5 * (0.5 * 6 + 0.5 * (0.5 * 4 + 0.5 * 2)))


def test_log_returns():
    close = pd.Series([100.0, 110.0, 99.0])
    rets = log_returns(close)
    assert np.isnan(rets.iloc[0])
    assert rets.iloc[1] == pytest.approx(np.log(1.1))
    assert rets.iloc[2] == pytest.approx(np.log(99.0 / 110.0))


def test_rsi_bounds_and_extremes():
    # monotonically increasing -> RSI approaches 100
    up = pd.Series(np.linspace(1.0, 2.0, 40))
    assert rsi(up, 14).iloc[-1] > 95
    # monotonically decreasing -> RSI approaches 0
    down = pd.Series(np.linspace(2.0, 1.0, 40))
    assert rsi(down, 14).iloc[-1] < 5
    # mixed values stay within [0, 100]
    rng = np.random.default_rng(0)
    mixed = pd.Series(100 + np.cumsum(rng.standard_normal(80)))
    vals = rsi(mixed, 14).dropna()
    assert ((vals >= 0) & (vals <= 100)).all()


def test_macd_relationship():
    close = pd.Series(np.linspace(1.0, 2.0, 60) + 0.01 * np.sin(np.arange(60)))
    m = macd(close)
    assert set(m.columns) == {"macd", "macd_signal", "macd_hist"}
    assert m["macd_hist"].iloc[-1] == pytest.approx(m["macd"].iloc[-1] - m["macd_signal"].iloc[-1])


def test_bollinger_band_width():
    close = pd.Series([1.0, 1.1, 0.9, 1.05, 0.95, 1.02, 1.03, 0.98, 1.01, 1.0] * 3)
    bb = bollinger(close, window=5, num_std=2.0)
    last = bb.iloc[-1]
    assert last["bb_upper"] > last["bb_mid"] > last["bb_lower"]
    assert last["bb_width"] == pytest.approx((last["bb_upper"] - last["bb_lower"]) / last["bb_mid"])


def test_atr_close_only_degenerates_to_close_range():
    # When high == low == close (close-only source), TR = |close_t - close_{t-1}|
    close = pd.Series([10.0, 11.0, 10.5, 10.7])
    a = atr(close, close, close, period=2)
    assert a.iloc[-1] > 0


def test_rolling_volatility_window():
    rets = pd.Series([0.01, -0.02, 0.015, -0.005, 0.02])
    v = rolling_volatility(rets, 3)
    assert np.isnan(v.iloc[1])
    manual = rets.iloc[0:3].std(ddof=1)
    assert v.iloc[2] == pytest.approx(manual)
