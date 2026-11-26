"""Tests for Phase 2 feature engineering: builders, leakage audit, selection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.features.builders import (
    build_core_features,
    build_cross_pair_features,
    build_feature_frame,
)
from app.services.features.leakage import (
    audit_perturb_future,
    audit_suspicious_correlation,
    run_leakage_audit,
)
from app.services.features.selection import (
    correlation_clustering,
    select_features,
    stability_selection,
)
from app.services.features.set import CORE_FEATURE_SET, FEATURE_SET_VERSION, get_feature_set
from app.services.features.store import load_features, save_features

RNG = np.random.default_rng(42)


def _bars(n: int = 250, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 1.0 + np.cumsum(rng.normal(0, 0.01, n))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2022-01-01", periods=n, freq="D"),
            "open": close * 0.999,
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
        }
    )


# ----------------------------------------------------------------------
# Builders
# ----------------------------------------------------------------------


class TestBuilders:
    def test_columns_match_registry(self):
        frame = build_feature_frame(_bars(300), {}, pair_symbol="EUR/USD")
        assert list(frame.columns) == ["pair_symbol", "timestamp", *CORE_FEATURE_SET.feature_names]

    def test_lookback_nan_pattern(self):
        frame = build_core_features(_bars(300))
        # ret_1d needs 2 bars -> first value at index 1
        assert pd.isna(frame["ret_1d"].iloc[0])
        assert frame["ret_1d"].notna().iloc[1]
        # zscore_20 needs 21 bars
        assert pd.isna(frame["zscore_20"].iloc[18])
        assert frame["zscore_20"].notna().iloc[25]
        # mom_60 needs 61 bars
        assert pd.isna(frame["mom_60"].iloc[58])
        assert frame["mom_60"].notna().iloc[61]

    def test_determinism(self):
        bars = _bars(200)
        a = build_feature_frame(bars, {})
        b = build_feature_frame(bars, {})
        pd.testing.assert_frame_equal(a, b)

    def test_rsi_extremes(self):
        n = 60
        close = np.arange(1, n + 1, dtype=float)  # strictly rising
        bars = pd.DataFrame(
            {
                "timestamp": pd.date_range("2022-01-01", periods=n, freq="D"),
                "open": close,
                "high": close + 1,
                "low": close - 0.5,
                "close": close,
            }
        )
        frame = build_core_features(bars)
        assert frame["rsi_14"].iloc[-1] == pytest.approx(100.0)

    def test_macd_positive_in_uptrend(self):
        n = 80
        close = np.exp(np.linspace(0, 1, n)) * 1.1
        bars = pd.DataFrame(
            {
                "timestamp": pd.date_range("2022-01-01", periods=n, freq="D"),
                "open": close,
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
            }
        )
        frame = build_core_features(bars)
        assert frame["macd_hist"].iloc[-1] > 0

    def test_cross_pair_with_no_legs_is_nan(self):
        frame = build_cross_pair_features(_bars(100), {})
        assert frame["usd_factor_20"].isna().all()

    def test_cross_pair_usd_factor_sign_flip(self):
        n = 80
        dates = pd.date_range("2022-01-01", periods=n, freq="D")
        up = pd.DataFrame(
            {
                "timestamp": dates,
                "open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "close": np.arange(1.0, n + 1.0),
            }
        )
        eurusd = pd.DataFrame(
            {"timestamp": dates, "open": 1.0, "high": 1.1, "low": 0.9, "close": np.full(n, 2.0)}
        )
        usdjpy = pd.DataFrame(
            {"timestamp": dates, "open": 1.0, "high": 1.1, "low": 0.9, "close": np.full(n, 5.0)}
        )
        frame = build_cross_pair_features(
            eurusd, {"EUR/USD": eurusd, "USD/JPY": usdjpy}, usd_pairs=["EUR/USD", "USD/JPY"]
        )
        # EUR/USD flat over 20d (0) and USD/JPY flat (0) -> factor 0
        assert frame["usd_factor_20"].iloc[40] == pytest.approx(0.0)
        frame2 = build_cross_pair_features(
            up, {"EUR/USD": up, "USD/JPY": usdjpy}, usd_pairs=["EUR/USD", "USD/JPY"]
        )
        # rising EUR/USD (+r) and flat USD/JPY (0, flipped) -> factor r/2 > 0
        assert frame2["usd_factor_20"].iloc[40] > 0


# ----------------------------------------------------------------------
# Leakage audit
# ----------------------------------------------------------------------


class TestLeakageAudit:
    def _target(self, bars: pd.DataFrame, horizon: int = 5) -> pd.Series:
        close = bars["close"]
        return np.log(close.shift(-horizon) / close)

    def test_builders_pass_perturb_future(self):
        bars = _bars(300)
        result = audit_perturb_future(bars, build_core_features)
        assert result["passed"] is True
        assert result["checked_rows"] == 150

    def test_harness_catches_leaky_builder(self):
        # A deliberately leaky "feature": tomorrow's close, backfilled.
        def leaky(df: pd.DataFrame) -> pd.DataFrame:
            out = build_core_features(df)
            out["leak"] = df["close"].shift(-1).bfill()
            return out

        bars = _bars(300)
        result = audit_perturb_future(bars, leaky)
        assert result["passed"] is False
        assert result["changed_rows"] > 0

    def test_suspicious_correlation_flags_target_copy(self):
        bars = _bars(300)
        frame = build_core_features(bars)
        target = self._target(bars)
        frame["copy_of_target"] = target
        result = audit_suspicious_correlation(frame, target)
        assert result["passed"] is False
        assert any(f["feature"] == "copy_of_target" for f in result["flagged"])

    def test_full_audit_on_core_set(self):
        bars = _bars(300)
        frame = build_feature_frame(bars, {}, pair_symbol="EUR/USD")
        target = self._target(bars)
        result = run_leakage_audit(
            bars, frame, target, lambda d: build_feature_frame(d, {}, pair_symbol="EUR/USD")
        )
        assert result.perturb_future["passed"] is True
        assert "caveat" in result.suspicious_correlation
        assert result.as_dict()["perturb_future"]["changed_rows"] == 0


# ----------------------------------------------------------------------
# Selection
# ----------------------------------------------------------------------


class TestSelection:
    def test_correlation_clustering_groups_duplicates(self):
        bars = _bars(300)
        frame = build_core_features(bars)
        frame["dup_ret_1d"] = frame["ret_1d"]  # exact duplicate
        clusters = correlation_clustering(
            frame[["ret_1d", "dup_ret_1d", "vol_cc_20"]], threshold=0.9
        )
        joined = {rep: members for rep, members in clusters.items()}
        flat = {c for rep, members in joined.items() for c in [rep, *members]}
        assert flat == {"ret_1d", "dup_ret_1d", "vol_cc_20"}
        assert any(len(members) == 1 for members in joined.values())

    def test_stability_selection_runs_and_reports(self):
        bars = _bars(400)
        frame = build_core_features(bars)
        target = np.log(bars["close"].shift(-5) / bars["close"])
        result = stability_selection(frame, target, n_splits=3, top_k=5)
        assert "selected" in result
        assert "selection_frequency" in result
        assert result["n_folds"] == 3

    def test_select_features_pipeline(self):
        bars = _bars(400)
        frame = build_feature_frame(bars, {}, pair_symbol="EUR/USD")
        target = np.log(bars["close"].shift(-5) / bars["close"])
        result = select_features(frame, target, n_splits=3, top_k=5)
        assert set(result.keys()) == {
            "selected",
            "correlation_clusters",
            "stability",
            "dropped_redundant",
        }
        assert isinstance(result["selected"], list)


# ----------------------------------------------------------------------
# Feature store
# ----------------------------------------------------------------------


class TestFeatureStore:
    def test_save_load_roundtrip(self, tmp_path):
        frame = build_feature_frame(_bars(200), {}, pair_symbol="EUR/USD")
        path = save_features(frame, "EUR/USD", base=tmp_path, meta={"seed": 1})
        assert path.exists()
        loaded = load_features("EUR/USD", base=tmp_path)
        assert loaded is not None
        assert len(loaded) == len(frame)
        assert load_features("USD/TRY", base=tmp_path) is None

    def test_feature_set_version_is_declared(self):
        assert get_feature_set().version == FEATURE_SET_VERSION
        assert get_feature_set().required_lookback >= 61
