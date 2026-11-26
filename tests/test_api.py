"""Core API endpoints with a temporary database (via conftest fixtures)."""

from __future__ import annotations

import time


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["price_bar_count"] > 0
    assert body["latest_data_timestamp"]
    assert body["latest_data_source"] == "demo"
    assert "not financial advice" in body["disclaimer"]


def test_pairs_list(client):
    r = client.get("/api/v1/pairs")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 2
    symbols = {p["symbol"] for p in body["pairs"]}
    assert "EUR/USD" in symbols
    eur = next(p for p in body["pairs"] if p["symbol"] == "EUR/USD")
    assert eur["is_demo"] is True
    assert eur["latest_price"] > 0
    assert eur["latest_timestamp"]


def test_current_price(client):
    r = client.get("/api/v1/pairs/EUR/USD/price")
    assert r.status_code == 200
    body = r.json()
    assert body["price"] > 0
    assert body["data_source"] == "demo"
    assert body["is_demo"] is True
    assert body["timestamp"]
    assert body["previous_close"] is not None
    assert body["change_abs"] is not None
    assert body["change_pct"] is not None


def test_history_chronological_and_limited(client):
    r = client.get("/api/v1/pairs/EUR/USD/history?limit=50")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 50
    stamps = [b["timestamp"] for b in body["bars"]]
    assert stamps == sorted(stamps)
    assert body["is_demo"] is True


def test_history_start_end_filters(client):
    r = client.get("/api/v1/pairs/EUR/USD/history?start=2020-01-01&end=2020-02-01")
    assert r.status_code == 200
    # demo data spans ~420 days back from today -> likely empty, shape must still hold
    assert r.json()["count"] == len(r.json()["bars"])


def test_invalid_pair_format(client):
    r = client.get("/api/v1/pairs/NOTAPAIR/price")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "invalid_pair_format"
    assert body["error"]["message"]


def test_unknown_pair_404(client):
    r = client.get("/api/v1/pairs/USD/PLN/price")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "pair_not_found"


def test_invalid_interval(client):
    r = client.get("/api/v1/pairs/EUR/USD/history?interval=1h")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_interval"


def test_validation_error_envelope(client):
    r = client.get("/api/v1/pairs/EUR/USD/history?limit=99999")
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]


def test_forecast_after_training(client):
    r = client.get("/api/v1/pairs/EUR/USD/forecast?horizon=1")
    assert r.status_code == 200
    body = r.json()
    assert body["horizon_days"] == 1
    assert body["interval_lower"] < body["interval_upper"]
    assert body["interval_level"] > 0.5
    assert body["model"]["model_name"]
    assert "not financial advice" in body["disclaimer"]
    assert body["is_demo"] is True


def test_forecast_without_model_404(client):
    r = client.get("/api/v1/pairs/USD/JPY/forecast?horizon=1")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "model_not_found"
    assert "train" in body["error"]["message"].lower()


def test_forecast_invalid_horizon(client):
    r = client.get("/api/v1/pairs/EUR/USD/forecast?horizon=0")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_indicators(client):
    r = client.get("/api/v1/pairs/EUR/USD/indicators")
    assert r.status_code == 200
    body = r.json()
    trend = body["trend"]
    assert trend["direction"] in ("up", "down", "sideways")
    assert 0 <= trend["strength"] <= 100
    assert trend["volatility_regime"] in ("low", "medium", "high")
    ind = trend["indicators"]
    assert "rsi_14" in ind and "macd" in ind and "atr_14" in ind


def test_models_endpoints(client):
    r = client.get("/api/v1/models")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert "lightgbm_available" in body

    r = client.get("/api/v1/models/EUR/USD")
    assert r.status_code == 200
    assert r.json()["count"] >= 1

    r = client.get("/api/v1/models/USD/JPY")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_metrics_endpoint(client):
    r = client.get("/api/v1/metrics/EUR/USD")
    assert r.status_code == 200
    body = r.json()
    assert body["pair_symbol"] == "EUR/USD"
    assert len(body["metrics"]) >= 2
    model_rows = [m for m in body["metrics"] if m["model_name"] not in ("naive", "drift")]
    baseline_rows = [m for m in body["metrics"] if m["model_name"] == "naive"]
    assert baseline_rows, "naive baseline must be reported"
    for m in model_rows:
        assert m["baseline_mae"] > 0
    assert "not financial advice" in body["disclaimer"]


def test_metrics_not_found(client):
    r = client.get("/api/v1/metrics/USD/JPY")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "metrics_not_found"


def test_jobs_auth_and_flow(client):
    # localhost (testclient) is allowed without a token
    r = client.post("/api/v1/jobs/collect-data", json={"pairs": ["EUR/USD"]})
    assert r.status_code == 200
    job = r.json()
    assert job["type"] == "collect-data"
    assert job["status"] in ("queued", "running")

    # poll to completion
    deadline = time.time() + 60
    status = job["status"]
    while time.time() < deadline:
        r = client.get(f"/api/v1/jobs/{job['id']}")
        assert r.status_code == 200
        status = r.json()["status"]
        if status in ("done", "failed"):
            break
        time.sleep(0.4)
    assert status == "done", r.json()

    # invalid pair -> 400
    r = client.post("/api/v1/jobs/train", json={"pairs": ["XYZ"]})
    assert r.status_code == 400

    # unknown job id -> 404
    r = client.get("/api/v1/jobs/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "job_not_found"


def test_unknown_route_error_envelope(client):
    r = client.get("/api/v1/no-such-route")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_dashboard_serves_persian_rtl(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert 'lang="fa"' in html
    assert 'dir="rtl"' in html
    assert "not financial advice" in html
    assert "chart.umd.js" in html


def test_openapi_documented(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for expected in (
        "/api/v1/health",
        "/api/v1/pairs",
        "/api/v1/pairs/{pair}/price",
        "/api/v1/pairs/{pair}/history",
        "/api/v1/pairs/{pair}/forecast",
        "/api/v1/pairs/{pair}/indicators",
        "/api/v1/models",
        "/api/v1/models/{pair}",
        "/api/v1/metrics/{pair}",
        "/api/v1/jobs/collect-data",
        "/api/v1/jobs/train",
        "/api/v1/jobs/{job_id}",
    ):
        assert expected in paths, f"missing route: {expected}"
