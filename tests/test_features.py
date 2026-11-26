"""Feature engineering with an explicit no-leakage test."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.features.engineering import (
    build_feature_frame,
    feature_columns,
    target_log_return,
)


def _synthetic_ohlc(n: int = 120, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.01))
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) * 1.002
    lows = np.minimum(opens, closes) * 0.998
    ts = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"timestamp": ts, "open": opens, "high": highs, "low": lows, "close": closes}
    )


HORIZONS = [1, 7]


def test_targets_are_strictly_future():
    df = _synthetic_ohlc()
    frame = build_feature_frame(df, HORIZONS)
    close = df["close"].to_numpy()
    h = 7
    for t in (10, 50, 100):
        expected = np.log(close[t + h] / close[t])
        assert frame[f"target_logret_h{h}"].iloc[t] == pytest.approx(expected)


def test_no_leakage_features_do_not_use_the_future():
    """Perturbing the future must not change any feature at time t."""
    df = _synthetic_ohlc(150, seed=3)
    cutoff = 100  # rows 0..100 are the 'past'

    frame_full = build_feature_frame(df, HORIZONS)
    df_truncated = df.iloc[: cutoff + 1].copy()
    frame_trunc = build_feature_frame(df_truncated, HORIZONS)

    feats = feature_columns()
    # Features up to the cutoff must be identical whether or not the future exists.
    left = frame_full.iloc[: cutoff + 1][feats]
    right = frame_trunc[feats]
    pd.testing.assert_frame_equal(
        left.reset_index(drop=True), right.reset_index(drop=True), check_exact=False, atol=1e-12
    )


def test_no_leakage_perturbing_future_close_changes_targets_only():
    df = _synthetic_ohlc(150, seed=5)
    frame_a = build_feature_frame(df, HORIZONS)

    df_b = df.copy()
    t = 90
    h = 7
    # Corrupt only a point strictly after t.
    df_b.loc[t + h, "close"] = df_b.loc[t + h, "close"] * 1.5
    frame_b = build_feature_frame(df_b, HORIZONS)

    feats = feature_columns()
    # Features at/before t are unchanged ...
    pd.testing.assert_frame_equal(
        frame_a.iloc[: t + 1][feats],
        frame_b.iloc[: t + 1][feats],
        check_exact=False,
        atol=1e-12,
    )
    # ... but the target at t changes.
    col = f"target_logret_h{h}"
    assert frame_a[col].iloc[t] != pytest.approx(frame_b[col].iloc[t])


def test_feature_frame_shape_and_no_target_leak_in_features():
    df = _synthetic_ohlc()
    frame = build_feature_frame(df, HORIZONS)
    feats = feature_columns()
    for col in feats:
        assert not col.startswith("target"), f"{col} must not be a model feature"
        assert col in frame.columns
    # Warm-up rows have NaN features; the tail rows have NaN targets.
    assert frame[feats].isna().any(axis=1).iloc[0]
    assert np.isnan(frame["target_logret_h7"].iloc[-1])


def test_target_log_return_helper():
    close = pd.Series([100.0, 105.0, 110.0])
    t = target_log_return(close, 2)
    assert t.iloc[0] == pytest.approx(np.log(1.1))
    assert np.isnan(t.iloc[1])
