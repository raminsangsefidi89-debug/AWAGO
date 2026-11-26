"""Tests for Phase 4: holdout protocol, stability, backtest simulation, regimes."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.evaluation.backtest import DISCLAIMER, simulate
from app.services.evaluation.holdout import evaluate_holdout, family_of, split_holdout
from app.services.evaluation.stability import stability_report
from app.services.features.regimes import cusum_change_points, regime_summary, vol_regime


class TestHoldout:
    def test_split_is_chronological(self):
        dev, hold = split_holdout(300, holdout_fraction=0.2, min_holdout=60)
        assert dev.max() < hold.min()
        assert len(hold) == 60
        assert len(dev) + len(hold) == 300

    def test_min_holdout_respected(self):
        _, hold = split_holdout(200, holdout_fraction=0.05, min_holdout=60)
        assert len(hold) == 60

    def test_family_of(self):
        assert family_of("baseline_naive") == "baseline"
        assert family_of("stat_arima") == "statistical"
        assert family_of("ml_ridge") == "ml"
        assert family_of("ensemble_avg") == "ensemble"

    def test_evaluate_holdout_picks_best_per_family(self):
        dev_results = {
            "baseline_naive": {"mae": 0.02},
            "baseline_drift": {"mae": 0.01},
            "ml_ridge": {"mae": 0.015},
            "ml_rf": {"mae": 0.012},
        }
        calls = []

        def run_rep(name):
            calls.append(name)
            return {"y_true": np.zeros(60), "preds": np.zeros(60), "metrics": {"mae": 0.02}}

        out = evaluate_holdout(dev_results, run_rep)
        assert out["protocol"] == "holdout-evaluated-once"
        assert set(out["families"]) == {"baseline", "ml"}
        assert out["families"]["baseline"]["representative"] == "baseline_drift"
        assert out["families"]["ml"]["representative"] == "ml_rf"
        assert out["families"]["ml"]["label"] == "held out, evaluated once"
        assert set(calls) == {"baseline_drift", "ml_rf"}

    def test_evaluate_holdout_records_errors(self):
        def run_rep(name):
            raise RuntimeError("boom")

        out = evaluate_holdout({"ml_ridge": {"mae": 0.1}}, run_rep)
        assert "error" in out["families"]["ml"]


class TestStability:
    def test_report_shape_and_caveat(self):
        n = 120
        rng = np.random.default_rng(1)
        y = rng.normal(size=n)
        yhat = y * 0.5 + rng.normal(size=n) * 0.1
        ts = pd.date_range("2021-01-01", periods=n, freq="D")
        close = pd.Series(1.0 + np.cumsum(rng.normal(0, 0.01, n)))
        report = stability_report(y, yhat, ts, close, "EUR/USD", "ml_ridge")
        assert set(report.keys()) == {
            "pair_symbol",
            "model_name",
            "by_year",
            "by_vol_regime",
            "caveat",
        }
        assert set(report["by_vol_regime"]) == {"low_vol", "mid", "high_vol"}
        assert "2021" in report["by_year"]
        assert "cherry-picking" in report["caveat"]

    def test_small_blocks_flagged(self):
        y = np.array([0.1, -0.2, 0.3])
        yhat = np.zeros(3)
        ts = pd.date_range("2021-01-01", periods=3, freq="D")
        close = pd.Series([1.0, 1.1, 1.0])
        report = stability_report(y, yhat, ts, close)
        assert "note" in report["by_year"]["2021"]


class TestBacktest:
    def test_perfect_forecast_profits(self):
        y = np.full(50, 0.001)
        yhat = np.full(50, 0.01)  # always predicts up, correctly
        result = simulate(y, yhat, cost_bps_per_side=1.0, slippage_bps_per_side=0.5)
        assert result["strategy"]["total_return"] > result["buy_and_hold"]["total_return"] - 0.01
        assert result["n_trades"] == 1  # one entry, never flips
        assert DISCLAIMER in result["disclaimer"]
        assert "deflated" in result["deflated_sharpe_caution"]

    def test_costs_are_charged(self):
        y = np.zeros(100)
        yhat = np.array([0.01, -0.01] * 50)  # flips every step
        result = simulate(y, yhat, cost_bps_per_side=10.0, slippage_bps_per_side=10.0)
        assert result["strategy"]["total_return"] < 0
        assert result["n_trades"] == 100

    def test_random_control_present(self):
        rng = np.random.default_rng(2)
        y = rng.normal(size=200) * 0.001
        yhat = rng.normal(size=200) * 0.001
        result = simulate(y, yhat, seed=7)
        assert {"strategy", "buy_and_hold", "random_control"} <= set(result)
        assert result["verdict_vs_random"].startswith("strategy ")

    def test_no_leverage_contract(self):
        y = np.ones(30) * 0.001
        yhat = np.ones(30)
        result = simulate(y, yhat)
        assert result["position"] == "sign of forecast, 1x notional, no leverage"
        # max possible gain: compounded 30 x 0.001 minus one entry cost
        assert result["strategy"]["total_return"] <= (1.001**30 - 1.0) + 1e-6


class TestRegimes:
    def test_vol_regime_point_in_time(self):
        rng = np.random.default_rng(3)
        close = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 120))))
        labels = vol_regime(close, window=20)
        assert len(labels) == 120
        assert labels.iloc[0] == "unknown"
        assert set(labels.iloc[45:].unique()) <= {"low_vol", "mid", "high_vol"}

    def test_regime_summary(self):
        rng = np.random.default_rng(4)
        close = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 120))))
        summary = regime_summary(close)
        assert sum(summary.values()) == 120

    def test_cusum_detects_shift(self):
        rng = np.random.default_rng(5)
        pre = rng.normal(0, 0.01, 100)
        post = rng.normal(0.05, 0.01, 100)  # clear mean shift
        rets = pd.Series(np.concatenate([pre, post]))
        points = cusum_change_points(rets, threshold=3.0)
        assert any(80 <= p <= 140 for p in points)
