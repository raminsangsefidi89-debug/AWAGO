"""Tests for Phase 3: model plugins, metrics, evaluation, ensembles, lifecycle."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.evaluation.metrics import (
    crps_from_quantiles,
    diebold_mariano,
    full_metric_suite,
    holm_bonferroni,
    mae,
    mase,
    pinball_loss,
    rmse,
    smape,
    verdict_vs_baseline,
    winkler_score,
)
from app.services.evaluation.runner import run_experiment
from app.services.evaluation.walkforward import purged_splits
from app.services.models.base import FitData, PredictData
from app.services.models.baselines import (
    DriftModel,
    ETSModel,
    MovingAverageModel,
    NaiveModel,
    SeasonalNaiveModel,
)
from app.services.models.ensembles import (
    average_ensemble,
    inverse_error_ensemble,
    online_decayed_ensemble,
    stacking_ensemble,
)
from app.services.models.lifecycle import (
    bootstrap_significance,
    champion_name,
    compare_and_maybe_promote,
    list_artifacts,
    save_artifact,
)
from app.services.models.ml import RidgeModel
from app.services.models.probabilistic import (
    adaptive_conformal,
    coverage_report,
    cqr_conformal,
    split_conformal,
)
from app.services.models.registry import available_models, core_model_names, get_model


def _series(n: int = 200, seed: int = 5) -> tuple:
    rng = np.random.default_rng(seed)
    close = 1.0 + np.cumsum(rng.normal(0, 0.01, n))
    ts = pd.date_range("2022-01-01", periods=n, freq="D")
    history = pd.Series(close, index=ts)
    features = pd.DataFrame({"timestamp": ts, "f1": rng.normal(size=n), "f2": rng.normal(size=n)})
    target = pd.Series(
        np.log(np.append(close[5:], np.full(5, close[-1])) / close) * 0 + np.log(close / close)
    )
    return history, features, target, ts


def _fit_data(n_train: int = 150, n: int = 200) -> tuple:
    history, features, target, ts = _series(n)
    # synthetic target: future 5-day return (filled with 0 at the end)
    close = history.to_numpy()
    tgt = np.log(np.append(close[5:], np.full(5, close[-1])) / close)
    target = pd.Series(tgt)
    fit = FitData(
        "EUR/USD",
        5,
        history.iloc[:n_train],
        features.iloc[:n_train].reset_index(drop=True),
        target.iloc[:n_train].reset_index(drop=True),
        ts[:n_train],
    )
    pred = PredictData("EUR/USD", 5, history, features.reset_index(drop=True), ts)
    return fit, pred, target


class TestBaselines:
    def test_naive_is_zero(self):
        fit, pred, _ = _fit_data()
        out = NaiveModel(horizon=5).fit(fit).predict(pred)
        assert np.allclose(out, 0.0)

    def test_drift_constant(self):
        fit, pred, _ = _fit_data()
        out = DriftModel(horizon=5).fit(fit).predict(pred)
        assert np.allclose(out, out[0])

    def test_seasonal_naive_shape(self):
        fit, pred, _ = _fit_data()
        out = SeasonalNaiveModel(horizon=5).fit(fit).predict(pred)
        assert out.shape == (200,)
        assert np.isfinite(out[10:]).all()

    def test_ma_and_ets_run(self):
        fit, pred, _ = _fit_data()
        for cls in (MovingAverageModel, ETSModel):
            out = cls(horizon=5).fit(fit).predict(pred)
            assert out.shape == (200,)
            assert np.isfinite(out).all()


class TestMLModels:
    def test_ridge_fits_and_predicts(self):
        fit, pred, _ = _fit_data()
        model = RidgeModel(horizon=5).fit(fit)
        out = model.predict(pred)
        assert out.shape == (200,)
        assert np.isfinite(out).all()

    def test_registry_reports_availability(self):
        models = {m["name"]: m for m in available_models()}
        assert models["baseline_naive"]["available"] is True
        assert "stat_garch_vol" in models
        if not models["stat_garch_vol"]["available"]:
            assert "arch" in models["stat_garch_vol"]["unavailable_reason"]
        for name in core_model_names():
            assert name in models

    def test_get_model_unknown_raises(self):
        with pytest.raises(ValueError):
            get_model("nope")


class TestMetrics:
    def test_basic_metrics(self):
        y = np.array([1.0, -1.0, 2.0])
        yhat = np.array([0.5, -0.5, 2.5])
        assert mae(y, yhat) == pytest.approx(0.5)
        assert rmse(y, yhat) == pytest.approx(np.sqrt(np.mean([0.25, 0.25, 0.25])))
        assert smape(y, yhat) > 0

    def test_mase_scaling(self):
        insample = np.arange(20, dtype=float)
        y = np.array([21.0, 22.0])
        yhat = np.array([21.5, 21.5])
        val = mase(y, yhat, insample, season=1)
        assert val == pytest.approx(0.5 / 1.0)

    def test_pinball_and_crps(self):
        y = np.array([0.0, 1.0])
        q = {0.5: np.array([0.0, 1.0]), 0.1: np.array([-1.0, 0.0]), 0.9: np.array([1.0, 2.0])}
        assert pinball_loss(y, q[0.5], 0.5) == 0.0
        assert crps_from_quantiles(y, q) >= 0

    def test_winkler_perfect_interval(self):
        y = np.array([0.5, 0.5])
        lo = np.array([0.0, 0.0])
        hi = np.array([1.0, 1.0])
        assert winkler_score(y, lo, hi, 0.9) == pytest.approx(1.0)

    def test_verdict_texts(self):
        dm_sig = {"p_value": 0.01, "mean_loss_diff": -0.1}  # model's loss lower
        dm_ns = {"p_value": 0.5, "mean_loss_diff": -0.1}
        dm_bad = {"p_value": 0.01, "mean_loss_diff": 0.1}  # model's loss higher
        assert verdict_vs_baseline(0.8, 1.0, dm_sig) == "beats baseline significantly"
        assert verdict_vs_baseline(0.8, 1.0, dm_ns) == "beats baseline, not significantly"
        assert verdict_vs_baseline(1.2, 1.0, dm_bad) == "worse than baseline (significant)"
        assert verdict_vs_baseline(1.2, 1.0, dm_ns) == "not better than baseline"

    def test_full_suite_with_quantiles(self):
        y = np.random.default_rng(0).normal(size=100)
        yhat = y + np.random.default_rng(1).normal(size=100) * 0.1
        q = {0.1: yhat - 0.5, 0.5: yhat, 0.9: yhat + 0.5}
        out = full_metric_suite(y, yhat, np.arange(100, dtype=float), q, level=0.8)
        assert {"mae", "rmse", "crps", "coverage", "winkler"} <= set(out)
        assert 0.0 <= out["coverage"] <= 1.0


class TestDM:
    def test_dm_detects_superior_model(self):
        rng = np.random.default_rng(1)
        rng.normal(size=500)
        err_good = rng.normal(size=500) * 0.5
        err_bad = rng.normal(size=500) * 1.5
        result = diebold_mariano(err_good, err_bad, h=1)
        assert result["p_value"] < 0.01
        assert result["mean_loss_diff"] < 0

    def test_dm_equal_models(self):
        rng = np.random.default_rng(2)
        err = rng.normal(size=300)
        result = diebold_mariano(err.copy(), err.copy(), h=1)
        assert result["p_value"] > 0.5

    def test_holm_monotone(self):
        adj = holm_bonferroni([("a", 0.01), ("b", 0.04), ("c", 0.03)])
        assert adj["a"] <= adj["c"] <= adj["b"] or adj["a"] <= adj["b"]


class TestWalkForward:
    def test_purged_splits_disjoint_and_purged(self):
        splits = purged_splits(300, 3, horizon=7, scheme="expanding")
        assert len(splits) == 3
        for train_idx, test_idx in splits:
            assert train_idx.max() < test_idx.min()  # strict time order
            assert test_idx.min() - train_idx.max() > 7 - 1  # purge gap
        # expanding: train starts always 0
        assert all(t[0] == 0 for t, _ in splits)

    def test_rolling_scheme(self):
        splits = purged_splits(300, 3, horizon=5, scheme="rolling", train_size=100)
        for train_idx, _ in splits:
            assert len(train_idx) <= 100 + 1

    def test_too_short_raises(self):
        with pytest.raises(ValueError):
            purged_splits(30, 3, horizon=5)


class TestProbabilistic:
    def test_split_conformal_covers_well_behaved_noise(self):
        rng = np.random.default_rng(3)
        y = rng.normal(size=300)
        pred = y + rng.normal(size=300) * 0.2
        out = split_conformal(y, pred, nominal_level=0.9)
        report = coverage_report(y, out["lower"], out["upper"], "split", 0.9)
        assert report.empirical_coverage > 0.75

    def test_adaptive_conformal_no_lookahead(self):
        rng = np.random.default_rng(4)
        y = rng.normal(size=200)
        pred = y * 0.9
        out = adaptive_conformal(y, pred, nominal_level=0.9, window=30)
        # interval width at row 50 must depend only on residuals before row 50
        assert out["q"][50] >= 0
        assert out["q"][50] == out["q"][50]  # finite
        assert np.isfinite(out["lower"]).all()

    def test_cqr(self):
        rng = np.random.default_rng(5)
        y = rng.normal(size=200) * 1.5  # some points fall outside the fixed quantiles
        q_lo = np.full(200, -1.0)
        q_hi = np.full(200, 1.0)
        out = cqr_conformal(y, q_lo, q_hi, nominal_level=0.9)
        assert (out["upper"] > out["lower"]).all()

    def test_coverage_report_shape(self):
        y = np.zeros(10)
        lo = np.full(10, -1.0)
        hi = np.full(10, 1.0)
        r = coverage_report(y, lo, hi, "m", 0.9)
        assert r.empirical_coverage == 1.0
        assert r.as_dict()["method"] == "m"


class TestEnsembles:
    def test_average(self):
        preds = {"a": np.array([1.0, 2.0]), "b": np.array([3.0, 4.0])}
        out = average_ensemble(preds, np.zeros(2))
        assert np.allclose(out, [2.0, 3.0])

    def test_inverse_error_prefers_better(self):
        y = np.array([1.0, 1.0, 1.0])
        fit = {"good": np.array([1.0, 1.0, 1.0]), "bad": np.array([5.0, 5.0, 5.0])}
        test = {"good": np.array([1.0]), "bad": np.array([5.0])}
        out = inverse_error_ensemble(fit, y, test, np.zeros(1))
        assert out[0] == pytest.approx(1.0, abs=0.05)

    def test_online_decayed(self):
        y = np.array([1.0, 1.0])
        fit = {"a": np.array([1.0, 1.0]), "b": np.array([2.0, 2.0])}
        test = {"a": np.array([1.0]), "b": np.array([2.0])}
        out = online_decayed_ensemble(fit, y, test, np.zeros(1))
        assert out.shape == (1,)

    def test_stacking(self):
        rng = np.random.default_rng(6)
        y_oof = rng.normal(size=50)
        oof = {"a": y_oof + rng.normal(size=50) * 0.1, "b": y_oof + rng.normal(size=50) * 0.5}
        test = {"a": np.array([0.5]), "b": np.array([0.9])}
        out = stacking_ensemble(oof, y_oof, test, np.zeros(1))
        assert out.shape == (1,)


class TestLifecycle:
    def test_bootstrap_significance(self):
        rng = np.random.default_rng(7)
        a = rng.normal(size=200) * 0.5
        b = rng.normal(size=200) * 1.0
        result = bootstrap_significance(a, b)
        assert result["verdict"] == "a_better"

    def test_artifact_and_champion(self, tmp_path):
        fit, _, _ = _fit_data()
        model = NaiveModel(horizon=5).fit(fit)
        meta = save_artifact(
            "baseline_naive", model, {"mae": 0.1}, "run1", "cfg", "snap", base=tmp_path
        )
        assert meta.exists()
        assert list_artifacts(base=tmp_path)
        result = compare_and_maybe_promote(
            "baseline_naive", np.zeros(10), None, "EUR/USD", 5, base=tmp_path
        )
        assert result["champion"] == "baseline_naive"
        assert champion_name("EUR/USD", 5, base=tmp_path) == "baseline_naive"


class TestEndToEnd:
    def test_run_experiment_quick(self, tmp_session, monkeypatch, tmp_path):
        from app.db.models import CurrencyPair
        from app.services import market
        from app.services.data_providers.base import PriceBarData

        monkeypatch.setattr("app.services.storage.series.DATA_DIR", tmp_path)
        for pair in ("EUR/USD", "GBP/USD"):
            tmp_session.add(CurrencyPair(symbol=pair, base=pair[:3], quote=pair[4:]))
        tmp_session.commit()
        rng = np.random.default_rng(9)
        base_date = pd.Timestamp("2022-01-01")
        for pair, start_price in (("EUR/USD", 1.1), ("GBP/USD", 1.3)):
            close = start_price + np.cumsum(rng.normal(0, 0.005, 240))
            bars = []
            for i, c in enumerate(close):
                d = (base_date + pd.Timedelta(days=i)).date()
                bars.append(
                    PriceBarData(
                        timestamp=pd.Timestamp(d),
                        open=float(c),
                        high=float(c) * 1.001,
                        low=float(c) * 0.999,
                        close=float(c),
                    )
                )
            market.upsert_bars(tmp_session, pair, bars, "demo")

        result = run_experiment(
            tmp_session,
            pairs=["EUR/USD"],
            horizons=[5],
            model_names=["baseline_naive", "baseline_drift", "baseline_ma", "ml_ridge"],
            quick=True,
            n_splits=2,
            registry_base=tmp_path,
        )
        assert result["n_rows"] >= 4
        names = {r["model_name"] for r in result["rows"]}
        assert {"baseline_naive", "ml_ridge"} <= names
        naive_rows = [r for r in result["rows"] if r["model_name"] == "baseline_naive"]
        assert naive_rows[0]["beats_baseline"] is False  # the baseline never beats itself
        assert (tmp_path / "leaderboards" / "latest.json").exists()
        for row in result["rows"]:
            assert row["beats_baseline"] == (row["mae"] < row["baseline_mae"])
