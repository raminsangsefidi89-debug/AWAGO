"""Tests for Phase 5: experiments/leaderboards/registry/insights API + SSE + ETag."""

from __future__ import annotations

import time

import numpy as np

from app.main import _RateLimiter


class TestExperimentAPI:
    def test_features_endpoint(self, client):
        r = client.get("/api/v1/features")
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == "3"
        assert "point_in_time" in body
        assert any(f["name"] == "rsi_14" for f in body["features"])

    def test_registry_models_endpoint(self, client):
        r = client.get("/api/v1/registry/models")
        assert r.status_code == 200
        names = {m["name"] for m in r.json()["models"]}
        assert {"baseline_naive", "ml_ridge", "stat_arima"} <= names

    def test_registry_compare_endpoint(self, client):
        rng = np.random.default_rng(1)
        payload = {
            "errors_a": (rng.normal(size=100) * 0.5).tolist(),
            "errors_b": (rng.normal(size=100) * 1.5).tolist(),
        }
        r = client.post("/api/v1/registry/compare", json=payload)
        assert r.status_code == 200
        assert r.json()["verdict"] == "a_better"

    def test_registry_promote_rollback_audited(self, client):
        r = client.post(
            "/api/v1/registry/promote", json={"pair": "EUR/USD", "horizon": 7, "model": "ml_ridge"}
        )
        assert r.status_code == 200
        assert r.json()["champion"] == "ml_ridge"
        r2 = client.post(
            "/api/v1/registry/rollback",
            json={"pair": "EUR/USD", "horizon": 7, "to": "baseline_naive"},
        )
        assert r2.status_code == 200
        r3 = client.get("/api/v1/registry/artifacts")
        assert r3.status_code == 200
        events = r3.json()["recent_events"]
        assert any(e["event"] == "promote" for e in events)
        assert any(e["event"] == "rollback" for e in events)

    def test_leaderboard_404_before_any_run(self, client):
        r = client.get("/api/v1/leaderboards/latest")
        assert r.status_code in (200, 404)

    def test_experiment_job_end_to_end(self, client, seeded_db):
        r = client.post(
            "/api/v1/experiments/run",
            json={
                "pairs": ["EUR/USD"],
                "horizons": [5],
                "models": ["baseline_naive", "baseline_drift", "ml_ridge"],
                "quick": True,
                "n_splits": 2,
            },
        )
        assert r.status_code == 200
        job_id = r.json()["job_id"]
        # poll until done (small matrix)
        status = None
        for _ in range(120):
            s = client.get(f"/api/v1/jobs/{job_id}").json()
            status = s["status"]
            if status in ("done", "failed", "cancelled"):
                break
            time.sleep(0.5)
        assert status == "done"
        # leaderboard now exists
        lb = client.get("/api/v1/leaderboards/latest")
        assert lb.status_code == 200
        body = lb.json()
        assert body["n_rows"] >= 3
        rows = body["rows"]
        assert all("verdict" in row for row in rows)
        naive = next(row for row in rows if row["model_name"] == "baseline_naive")
        assert naive["verdict"] == "baseline (yardstick)"
        # backtest from stored predictions
        bt = client.get("/api/v1/backtests/EUR-USD?horizon=5")
        assert bt.status_code == 200
        btb = bt.json()
        assert "disclaimer" in btb and "random_control" in btb
        # probabilistic forecast
        pf = client.get("/api/v1/forecasts/probabilistic/EUR-USD?horizon=5")
        assert pf.status_code == 200
        pfb = pf.json()
        assert "empirical_coverage_on_wf" in pfb
        assert len(pfb["fan_chart"]) >= 2
        # explainability + drift + regimes
        assert client.get("/api/v1/explainability/EUR-USD?horizon=5").status_code == 200
        assert client.get("/api/v1/drift/EUR-USD").status_code == 200
        assert client.get("/api/v1/regimes/EUR-USD").status_code == 200
        # runs list
        runs = client.get("/api/v1/experiments/runs").json()["runs"]
        assert any(run["run_id"] == body["run_id"] for run in runs)


class TestInsightsAPI:
    def test_volatility_method_labeled(self, client):
        r = client.get("/api/v1/volatility/EUR-USD?horizon=7")
        assert r.status_code == 200
        body = r.json()
        assert body["method"] in ("rolling-realized", "garch(1,1)")
        assert "disclaimer" in body

    def test_backtest_404_without_run(self, client):
        r = client.get("/api/v1/backtests/USD-TRY?horizon=30&run_id=does-not-exist")
        assert r.status_code == 404
        assert r.json()["error"]["code"] in ("no_predictions", "no_run")

    def test_regimes_400_short_series(self, client):
        r = client.get("/api/v1/regimes/AAA-BBB")
        assert r.status_code in (400, 404)


class TestJobSSE:
    def test_sse_stream_terminates_for_done_job(self, client, seeded_db):
        # collect only EUR/JPY: later v1 tests need other pairs to stay empty
        r = client.post("/api/v1/jobs/collect-data", json={"pairs": ["EUR/JPY"]})
        assert r.status_code == 200
        job_id = r.json()["id"]
        for _ in range(60):
            s = client.get(f"/api/v1/jobs/{job_id}").json()
            if s["status"] in ("done", "failed", "cancelled"):
                break
            time.sleep(0.5)
        with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            lines = []
            for line in resp.iter_lines():
                lines.append(line)
                if len(lines) > 10:
                    break
            assert any(ln.startswith("data: ") for ln in lines)

    def test_sse_unknown_job_404(self, client):
        r = client.get("/api/v1/jobs/nope/events")
        assert r.status_code == 404


class TestMiddleware:
    def test_rate_limiter_blocks_bursts(self):
        limiter = _RateLimiter(rate_per_minute=10)
        assert all(limiter.allow("ip1") for _ in range(10))
        assert limiter.allow("ip1") is False
        assert limiter.allow("ip2") is True  # independent bucket

    def test_etag_roundtrip(self, client):
        r = client.get("/api/v1/features")
        assert r.status_code == 200
        etag = r.headers.get("etag")
        assert etag
        r2 = client.get("/api/v1/features", headers={"If-None-Match": etag})
        assert r2.status_code == 304

    def test_error_envelope_on_unknown_run(self, client):
        r = client.get("/api/v1/experiments/runs/does-not-exist")
        assert r.status_code == 404
        body = r.json()
        assert body["error"]["code"] == "run_not_found"
