"""Training pipeline: artifacts, honest baseline comparison, model persistence."""

from __future__ import annotations

import pytest

from app.db.engine import session_scope
from app.db.models import MetricRecord, ModelArtifact
from app.services.forecasting.inference import forecast_pair
from app.services.forecasting.training import lightgbm_available, train_pair


def test_quick_training_creates_artifacts_and_honest_metrics(trained_db, app_env):
    settings = app_env
    with session_scope() as session:
        artifacts = [a for a in session.query(ModelArtifact).all() if a.pair_symbol == "EUR/USD"]
        assert len(artifacts) >= 1
        art = artifacts[0]
        assert art.horizon == 1
        assert art.n_rows > 100
        assert art.data_source == "demo"

        metrics = [m for m in session.query(MetricRecord).all() if m.pair_symbol == "EUR/USD"]
        names = {m.model_name for m in metrics}
        assert "naive" in names, "baseline metrics must be recorded"
        for m in metrics:
            # Every model row records the naive baseline error for comparison.
            assert m.baseline_mae > 0
            assert m.n_test > 0
            # beats_baseline must be consistent with the recorded errors.
            if m.model_name not in ("naive", "drift"):
                assert m.beats_baseline == (m.mae < m.baseline_mae)


def test_forecast_output_shape(trained_db, app_env):
    with session_scope() as session:
        f = forecast_pair(session, "EUR/USD", 1, settings=app_env)
    assert f["horizon_days"] == 1
    assert f["interval_lower"] < f["interval_upper"]
    assert f["is_demo"] is True
    assert f["data_source"] == "demo"
    assert f["last_data_timestamp"]
    assert f["model"]["model_name"]
    assert "disclaimer" not in f  # disclaimer added by the API schema layer


def test_lightgbm_option_is_reported(trained_db):
    # The function must return a bool either way (graceful optional dependency).
    assert isinstance(lightgbm_available(), bool)


def test_training_fails_cleanly_without_enough_data(seeded_db, app_env):
    from app.db.engine import session_scope
    from app.services.market import upsert_bars

    with session_scope() as session:
        upsert_bars(session, "EUR/GBP", [], data_source="demo")  # ensure pair exists implicitly
    with pytest.raises((ValueError, Exception)) as excinfo:
        with session_scope() as session:
            train_pair(session, "EUR/GBP", horizons=[1], settings=app_env, quick=True)
    assert "bars" in str(excinfo.value).lower() or "train" in str(excinfo.value).lower()
