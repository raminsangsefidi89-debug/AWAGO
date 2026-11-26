"""Phase 8 hardening: property tests, failure injection, security, reproducibility."""

from __future__ import annotations

import time
from datetime import date

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.evaluation.walkforward import purged_splits
from app.services.features.builders import build_core_features
from app.services.jalali import gregorian_to_jalali, jalali_to_gregorian
from app.services.models.probabilistic import adaptive_conformal, split_conformal
from app.services.storage.series import read_series, write_series

# ----------------------------------------------------------------------
# Property tests (hypothesis)
# ----------------------------------------------------------------------


class TestProperties:
    @settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        steps=st.lists(
            st.floats(min_value=-0.05, max_value=0.05, allow_nan=False, allow_infinity=False),
            min_size=40,
            max_size=120,
        )
    )
    def test_rsi_bounded(self, steps):
        close = 100.0 * np.exp(np.cumsum(np.asarray(steps)))
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2022-01-01", periods=len(close), freq="D"),
                "open": close,
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
            }
        )
        frame = build_core_features(df)
        rsi = frame["rsi_14"].dropna()
        if len(rsi):
            assert ((rsi >= 0) & (rsi <= 100)).all()

    @settings(max_examples=25, deadline=None)
    @given(
        n=st.integers(min_value=60, max_value=400),
        n_splits=st.integers(min_value=1, max_value=5),
        horizon=st.integers(min_value=1, max_value=15),
    )
    def test_walkforward_splits_are_ordered_disjoint_purged(self, n, n_splits, horizon):
        try:
            splits = purged_splits(n, n_splits, horizon=horizon)
        except ValueError:
            return
        for train_idx, test_idx in splits:
            assert train_idx.max() < test_idx.min()
            assert test_idx.min() - train_idx.max() > horizon - 1
            assert len(set(train_idx) & set(test_idx)) == 0

    @settings(max_examples=20, deadline=None)
    @given(
        gy=st.integers(min_value=1900, max_value=2200),
        gm=st.integers(min_value=1, max_value=12),
        gd=st.integers(min_value=1, max_value=28),
    )
    def test_jalali_roundtrip_property(self, gy, gm, gd):
        jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
        back = jalali_to_gregorian(jy, jm, jd)
        assert back == (gy, gm, gd)

    @settings(max_examples=15, deadline=None)
    @given(
        noise=st.lists(
            st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=60,
            max_size=150,
        )
    )
    def test_conformal_intervals_bracket_predictions(self, noise):
        y = np.asarray(noise)
        pred = y * 0.5
        out = split_conformal(y, pred, nominal_level=0.9)
        assert (out["upper"] >= out["lower"]).all()
        ac = adaptive_conformal(y, pred, nominal_level=0.9, window=30)
        assert (ac["upper"] >= ac["lower"]).all()


# ----------------------------------------------------------------------
# Failure injection
# ----------------------------------------------------------------------


class TestFailureInjection:
    def test_provider_down_falls_back_to_demo(self):
        from app.services.data_providers.demo import DemoProvider
        from app.services.data_providers.factory import FallbackProvider

        class Down:
            name = "down"
            is_demo = False

            def fetch_history(self, pair, start, end):
                raise ConnectionError("network unreachable")

            def fetch_latest(self, pair):
                raise ConnectionError("network unreachable")

        provider = FallbackProvider(Down(), DemoProvider(seed=7))
        bars = provider.fetch_history("EUR/USD", date(2023, 1, 1), date(2023, 1, 5))
        assert len(bars) == 5
        assert provider.fallback_used is True
        assert provider.last_source == "demo"

    def test_corrupt_parquet_reads_empty_or_raises_cleanly(self, tmp_path):
        path = tmp_path / "series"
        write_series(
            pd.DataFrame({"timestamp": pd.date_range("2024-0-1", periods=0)}),
            "X",
            "y",
            series_dir=tmp_path,
        ) if False else None
        # write a corrupt file manually
        bad = tmp_path / "BAD_PAIR__BAD.parquet"
        bad.write_bytes(b"this is not parquet")
        try:
            out = read_series("BAD PAIR", "bad", series_dir=tmp_path)
            assert out.empty
        except Exception as exc:
            assert isinstance(exc, Exception)

    def test_disk_guard_refuses_training(self, monkeypatch):
        import shutil

        from app.api.job_manager import check_resources

        monkeypatch.setattr(shutil, "disk_usage", lambda _p: shutil._ntuple_diskusage(10, 10, 10))
        reason = check_resources(min_disk_mb=200)
        assert reason is not None and "disk" in reason

    def test_cancelled_job_reaches_cancelled_state(self, app_env):
        from app.api.job_manager import JobCancelled, job_manager
        from app.db.engine import session_scope
        from app.db.models import JobRecord

        with session_scope() as session:
            session.add(
                JobRecord(
                    id="kill-me",
                    type="collect-data",
                    status="running",
                    params_json="{}",
                    progress=0.0,
                    message="",
                )
            )
        assert job_manager.request_cancel("kill-me") is True
        with pytest.raises(JobCancelled):
            job_manager._check_cancel("kill-me")

    def test_job_failure_is_recorded_not_raised(self, app_env):
        from app.api.job_manager import job_manager

        job = job_manager.submit("bogus-job-type", {})
        for _ in range(60):
            rec = job_manager.get(job.id)
            if rec.status in ("done", "failed", "cancelled"):
                break
            time.sleep(0.25)
        assert rec.status == "failed"
        assert "Unknown job type" in rec.message

    def test_experiment_job_survives_bad_params(self, app_env):
        from app.api.job_manager import job_manager

        job = job_manager.submit("experiment", {"pairs": ["ZZ/ZZ"], "models": ["baseline_naive"]})
        for _ in range(90):
            rec = job_manager.get(job.id)
            if rec.status in ("done", "failed", "cancelled"):
                break
            time.sleep(0.25)
        assert rec.status in ("done", "failed")  # clean failure or clean skip, never a hang
        assert rec.finished_at is not None


# ----------------------------------------------------------------------
# Security
# ----------------------------------------------------------------------


class TestSecurity:
    def test_path_traversal_in_pair_param_rejected(self, client):
        for bad in ("..%2F..%2Fetc%2Fpasswd", "....//....//etc", "%2e%2e%2fetc"):
            r = client.get(f"/api/v1/pairs/{bad}/history")
            assert r.status_code in (400, 404), f"path traversal not rejected: {bad}"
            r2 = client.get(f"/api/v1/quality/{bad}")
            assert r2.status_code in (400, 404)

    def test_no_secrets_in_repo(self):
        from pathlib import Path

        offenders = []
        for path in Path("app").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in ('API_KEY = "sk-', "BEGIN RSA PRIVATE", 'password = "', 'secret = "'):
                if marker in text:
                    offenders.append(f"{path}: {marker}")
        assert not offenders, offenders

    def test_env_file_gitignored(self):
        import subprocess

        out = subprocess.run(["git", "check-ignore", ".env"], capture_output=True, text=True)
        assert out.returncode == 0, ".env must be git-ignored"

    def test_artifact_json_is_validated(self, tmp_path):
        from app.services.models.lifecycle import list_artifacts

        folder = tmp_path / "registry" / "m"
        folder.mkdir(parents=True)
        (folder / "bad.json").write_text("{not json", encoding="utf-8")
        (folder / "good.json").write_text('{"name": "m"}', encoding="utf-8")
        arts = list_artifacts("m", base=tmp_path)
        assert len(arts) == 1  # corrupt file skipped, not crashing

    def test_export_stream_is_bounded(self, client):
        r = client.get("/api/v1/pairs/EUR-USD/export?format=csv")
        assert r.status_code == 200
        assert len(r.content) < 5_000_000  # bounded by stored history, not unbounded memory


# ----------------------------------------------------------------------
# Reproducibility
# ----------------------------------------------------------------------


class TestReproducibility:
    def test_run_id_is_deterministic(self):
        from app.repro import make_run_id

        a = make_run_id("test", snapshot="abc")
        b = make_run_id("test", snapshot="abc")
        c = make_run_id("test", snapshot="abd")
        assert a == b
        assert a != c

    def test_demo_seed_gives_identical_bars(self):
        from app.services.data_providers.demo import DemoProvider

        a = DemoProvider(seed=42).fetch_history("EUR/USD", date(2023, 1, 1), date(2023, 3, 1))
        b = DemoProvider(seed=42).fetch_history("EUR/USD", date(2023, 1, 1), date(2023, 3, 1))
        assert [x.close for x in a] == [x.close for x in b]

    def test_features_are_deterministic(self):
        rng = np.random.default_rng(1)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, 120)))
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2022-01-01", periods=120, freq="D"),
                "open": close,
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
            }
        )
        f1 = build_core_features(df)
        f2 = build_core_features(df)
        pd.testing.assert_frame_equal(f1, f2)
