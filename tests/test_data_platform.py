"""Tests for Phase 1 data platform: quality engine, resilience, providers, store."""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy.exc
from sqlalchemy import create_engine, text

from app.services.data_providers.base import PriceBarData, ProviderError
from app.services.data_providers.capabilities import ProviderCapabilities
from app.services.data_providers.csv_import import CSVImportProvider
from app.services.data_providers.factory import (
    FallbackProvider,
    ResilientProvider,
    all_capabilities,
)
from app.services.data_providers.resilience import (
    CircuitBreaker,
    TTLCache,
    backoff_delay,
    with_backoff,
)
from app.services.quality.engine import (
    build_quality_report,
    find_gaps,
    find_outliers,
    find_stale,
    triangular_consistency,
    validate_ohlc,
)
from app.services.storage.series import delete_series, read_series, write_series


def _frame(
    days: int = 60, start: str = "2024-01-01", gaps: list[int] | None = None
) -> pd.DataFrame:
    ts = pd.date_range(start, periods=days, freq="D")
    if gaps:
        ts = ts.delete(sorted(gaps))
    close = pd.Series(range(len(ts)), dtype=float) + 100.0
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
        }
    )


# ----------------------------------------------------------------------
# Quality engine
# ----------------------------------------------------------------------


class TestQualityEngine:
    def test_find_gaps_calendar_cadence(self):
        df = _frame(gaps=[10, 11, 30])
        gaps = find_gaps(df)
        assert gaps["cadence"] == "calendar_day"
        assert gaps["missing_count"] == 3

    def test_find_gaps_business_cadence(self):
        ts = pd.bdate_range("2024-01-01", periods=60)
        ts = ts.delete([5, 6])  # drop two business days
        df = pd.DataFrame({"timestamp": ts, "close": range(len(ts))})
        gaps = find_gaps(df)
        assert gaps["cadence"] == "business_day"
        assert gaps["missing_count"] == 2

    def test_stale_detection(self):
        old = _frame(days=30, start="2020-01-01")
        assert find_stale(old)["is_stale"] is True
        fresh = _frame(days=30, start=(date.today() - timedelta(days=30)).isoformat())
        assert find_stale(fresh)["is_stale"] is False

    def test_outlier_detection_finds_spike(self):
        df = _frame(days=60)
        df.loc[30, "close"] = 300.0  # huge up-move then back
        result = find_outliers(df)
        assert result["outlier_count"] >= 1

    def test_ohlc_validation(self):
        good = _frame(days=10)
        assert validate_ohlc(good)["valid"] is True
        bad = _frame(days=10)
        bad.loc[3, "high"] = bad.loc[3, "close"] - 5  # violates high >= max(o,c)
        result = validate_ohlc(bad)
        assert result["valid"] is False
        assert result["bad_rows"] == 1

    def test_triangular_consistency(self):
        n = 30
        gbpusd = pd.DataFrame(
            {"timestamp": pd.date_range("2024-01-01", periods=n), "close": [1.25] * n}
        )
        eurgbp = pd.DataFrame(
            {"timestamp": pd.date_range("2024-01-01", periods=n), "close": [0.85] * n}
        )
        eurusd = pd.DataFrame(
            {"timestamp": pd.date_range("2024-01-01", periods=n), "close": [1.0625] * n}
        )
        legs = {"EUR/USD": eurusd, "GBP/USD": gbpusd, "EUR/GBP": eurgbp}
        ok = triangular_consistency(legs, tolerance=0.005)
        assert ok["applicable"] is True
        assert ok["violation_count"] == 0
        eurusd_bad = eurusd.copy()
        eurusd_bad["close"] = 1.30  # 22% off the implied rate
        bad = triangular_consistency({**legs, "EUR/USD": eurusd_bad}, tolerance=0.005)
        assert bad["violation_count"] == n

    def test_full_report_demo_skips_triangular(self):
        df = _frame(days=40)
        report = build_quality_report("EUR/USD", "demo", df, is_demo=True)
        assert report["triangular_consistency"]["applicable"] is False
        assert report["summary"]["status"] in ("clean", "issues_found")
        json.dumps(report)  # JSON-safe


# ----------------------------------------------------------------------
# Resilience
# ----------------------------------------------------------------------


class TestResilience:
    def test_circuit_breaker_opens_and_recovers(self):
        cb = CircuitBreaker(failure_threshold=2, reset_seconds=60.0)
        assert cb.allow() is True
        cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "open"
        assert cb.allow() is False  # inside the reset window
        cb.opened_at = time.monotonic() - 61  # simulate elapsed reset window
        assert cb.allow() is True  # half-open probe
        cb.record_success()
        assert cb.state == "closed"

    def test_ttl_cache(self):
        cache = TTLCache(ttl_seconds=60.0)
        cache.set("k", [1, 2])
        assert cache.get("k") == [1, 2]
        cache2 = TTLCache(ttl_seconds=0.0)
        cache2.set("k", 1)
        time.sleep(0.01)
        assert cache2.get("k") is None

    def test_backoff_and_with_backoff(self):
        assert backoff_delay(0, base=1.0, jitter=False) == 1.0
        assert backoff_delay(10, base=1.0, cap=30.0, jitter=False) == 30.0
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("boom")
            return "ok"

        assert with_backoff(flaky, retries=3, sleep=lambda _s: None) == "ok"
        with pytest.raises(ValueError):
            with_backoff(
                lambda: (_ for _ in ()).throw(ValueError("x")), retries=2, sleep=lambda _s: None
            )

    def test_resilient_provider_cache_and_breaker(self):
        calls = []

        class Flaky:
            name = "flaky"
            is_demo = False

            def fetch_history(self, pair, start, end):
                calls.append(1)
                if len(calls) == 1:
                    raise RuntimeError("down")
                return [PriceBarData(timestamp=date(2024, 1, 1), open=1, high=1, low=1, close=1)]

            def fetch_latest(self, pair):
                return None

        provider = ResilientProvider(Flaky(), failure_threshold=3, cache_ttl_seconds=60.0)
        with pytest.raises(RuntimeError):
            provider.fetch_history("EUR/USD", date(2024, 1, 1), date(2024, 1, 2))
        bars = provider.fetch_history("EUR/USD", date(2024, 1, 1), date(2024, 1, 2))
        assert len(bars) == 1
        assert len(calls) == 2  # second call hits the provider...
        provider.fetch_history("EUR/USD", date(2024, 1, 1), date(2024, 1, 2))
        assert len(calls) == 2  # ...third is served from cache

    def test_fallback_provider_labels_source(self):
        class Down:
            name = "down"
            is_demo = False

            def fetch_history(self, pair, start, end):
                raise RuntimeError("down")

            def fetch_latest(self, pair):
                raise RuntimeError("down")

        from app.services.data_providers.demo import DemoProvider

        provider = FallbackProvider(Down(), DemoProvider(seed=1))
        bars = provider.fetch_history("EUR/USD", date(2023, 1, 1), date(2023, 1, 5))
        assert len(bars) == 5
        assert provider.fallback_used is True
        assert provider.last_source == "demo"


# ----------------------------------------------------------------------
# Providers
# ----------------------------------------------------------------------


class TestProviders:
    def test_csv_import_provider(self, tmp_path: Path):
        csv_file = tmp_path / "EURUSD.csv"
        content = (
            "date,open,high,low,close\n"
            "2024-01-01,1.1,1.2,1.0,1.15\n"
            "2024-01-02,1.15,1.25,1.05,1.2\n"
            "bad-date,1,1,1,1\n"
            # high < max(o,c) -> skipped as invalid
            "2024-01-03,1.2,1.1,1.0,1.15\n"
        )
        csv_file.write_text(content, encoding="utf-8")
        provider = CSVImportProvider(tmp_path)
        bars = provider.fetch_history("EUR/USD", date(2024, 1, 1), date(2024, 1, 31))
        assert len(bars) == 2
        assert bars[0].close == 1.15
        with pytest.raises(ProviderError):
            provider.fetch_history("GBP/USD", date(2024, 1, 1), date(2024, 1, 31))

    def test_stooq_parses_canned_csv(self, monkeypatch):
        from app.services.data_providers import stooq as stooq_mod

        class FakeResponse:
            status_code = 200
            text = (
                "Date,Open,High,Low,Close,Volume\n"
                "2024-01-02,1.10,1.12,1.09,1.11,0\n"
                "2024-01-03,1.11,1.13,1.10,1.12,0\n"
            )

        monkeypatch.setattr(stooq_mod, "http_get_with_retries", lambda *a, **k: FakeResponse())
        provider = stooq_mod.StooqProvider()
        bars = provider.fetch_history("EUR/USD", date(2024, 1, 1), date(2024, 1, 31))
        assert [b.close for b in bars] == [1.11, 1.12]
        with pytest.raises(ProviderError):
            provider.fetch_history("BADPAIR", date(2024, 1, 1), date(2024, 1, 31))

    def test_capabilities_declare_verification_status(self):
        caps = {c["name"]: c for c in all_capabilities()}
        assert caps["demo"]["is_demo"] is True
        assert caps["demo"]["verified_live"] is True
        assert caps["frankfurter"]["verified_live"] is False
        assert caps["stooq"]["verified_live"] is False
        assert caps["csv_import"]["verified_live"] is True
        assert caps["frankfurter"]["requires_key"] is False

    def test_capabilities_supports_pair(self):
        cap = ProviderCapabilities(name="x", pairs=("EUR/USD", "GBP/USD"))
        assert cap.supports_pair("eur/usd") is True
        assert cap.supports_pair("USD/JPY") is False


# ----------------------------------------------------------------------
# Series store
# ----------------------------------------------------------------------


class TestSeriesStore:
    def test_write_read_roundtrip(self, tmp_path: Path):
        df = _frame(days=10)
        write_series(df, "EUR/USD", "demo", series_dir=tmp_path)
        out = read_series("EUR/USD", "demo", series_dir=tmp_path)
        assert len(out) == 10
        out2 = read_series(
            "EUR/USD", "demo", start="2024-01-05", end="2024-01-07", series_dir=tmp_path
        )
        assert len(out2) == 3
        assert delete_series("EUR/USD", "demo", series_dir=tmp_path) is True
        assert read_series("EUR/USD", "demo", series_dir=tmp_path).empty

    def test_missing_series_is_empty(self, tmp_path: Path):
        assert read_series("USD/TRY", "stooq", series_dir=tmp_path).empty


# ----------------------------------------------------------------------
# Provenance + migration
# ----------------------------------------------------------------------


class TestProvenanceAndMigration:
    def test_migration_0002_adds_provenance_and_check(self, tmp_path: Path):
        import os
        import subprocess
        import sys

        db_path = tmp_path / "mig.db"
        env_db = f"sqlite+pysqlite:///{db_path}"
        env = dict(os.environ, DATABASE_URL=env_db)

        def run_alembic(*args: str) -> subprocess.CompletedProcess:
            code = (
                "from alembic.config import Config;"
                "from alembic import command;"
                f"c = Config('alembic.ini'); command.upgrade(c, '{args[-1]}')"
            )
            return subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
            )

        # True legacy path: schema at revision 0001 (exact v1), row inserted,
        # then upgraded to head (0002) — the row must survive the batch rebuild.
        run = run_alembic("upgrade", "0001")
        assert run.returncode == 0, run.stderr
        engine = create_engine(env_db)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO price_bars (pair_symbol, timestamp, interval, open, high, low, close, volume,"
                    " data_source, is_demo, created_at)"
                    " VALUES ('EUR/USD', '2024-01-01', '1d', 1, 1, 1, 1, NULL, 'demo', 1, '2024-01-01')"
                )
            )
        engine.dispose()
        run = run_alembic("upgrade", "head")
        assert run.returncode == 0, run.stderr
        engine = create_engine(env_db)
        with engine.begin() as conn:
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(price_bars)"))}
            assert {"fetched_at", "dataset_version", "quality_flag"} <= cols
            # v1 row preserved
            assert conn.execute(text("SELECT COUNT(*) FROM price_bars")).scalar() == 1
            # CHECK rejects an inconsistent demo/source pair
            with pytest.raises(sqlalchemy.exc.IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO price_bars (pair_symbol, timestamp, interval, open, high, low, close,"
                        " data_source, is_demo, created_at, dataset_version, quality_flag)"
                        " VALUES ('EUR/USD', '2024-01-02', '1d', 1, 1, 1, 1, 'demo', 0, '2024-01-01', '', 'ok')"
                    )
                )
        engine.dispose()

    def test_upsert_sets_provenance_and_mirror(self, tmp_session, tmp_path, monkeypatch):
        from app.db.models import PriceBar
        from app.services import market

        monkeypatch.setattr("app.services.storage.series.DATA_DIR", tmp_path)
        bars = [
            PriceBarData(timestamp=date(2024, 1, d), open=1, high=2, low=0.5, close=1.5)
            for d in (1, 2, 3)
        ]
        market.upsert_bars(tmp_session, "EUR/USD", bars, "demo")
        rows = tmp_session.query(PriceBar).filter(PriceBar.pair_symbol == "EUR/USD").all()
        assert len(rows) == 3
        assert all(r.dataset_version.startswith("demo:") for r in rows)
        assert all(r.quality_flag == "ok" for r in rows)
        assert all(r.fetched_at is not None for r in rows)
        # Parquet mirror written
        assert (tmp_path / "series" / "EUR_USD__DEMO.parquet").exists()


# ----------------------------------------------------------------------
# API surface
# ----------------------------------------------------------------------


class TestDataPlatformAPI:
    def test_quality_endpoint(self, client):
        r = client.get("/api/v1/quality/EUR-USD?refresh=true")
        assert r.status_code == 200
        body = r.json()
        assert body["pair_symbol"] == "EUR/USD"
        assert body["summary"]["status"] in ("clean", "issues_found")
        r2 = client.get("/api/v1/quality/EUR-USD")  # stored report
        assert r2.status_code == 200

    def test_providers_endpoint(self, client):
        r = client.get("/api/v1/providers")
        assert r.status_code == 200
        body = r.json()
        names = {p["name"] for p in body["providers"]}
        assert {"demo", "frankfurter", "stooq", "csv_import"} <= names
        assert "note" in body

    def test_export_csv(self, client):
        r = client.get("/api/v1/pairs/EUR-USD/export?format=csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert r.text.splitlines()[0].startswith("timestamp,open,high,low,close")
        r2 = client.get("/api/v1/pairs/EUR-USD/export?format=parquet")
        assert r2.status_code == 200
        assert len(r2.content) > 100

    def test_job_cancel_unknown_404(self, client):
        r = client.post("/api/v1/jobs/does-not-exist/cancel")
        assert r.status_code == 404


# ----------------------------------------------------------------------
# Job manager helpers
# ----------------------------------------------------------------------


class TestJobGuards:
    def test_check_resources_reports_or_passes(self):
        from app.api.job_manager import check_resources

        result = check_resources(min_disk_mb=0, min_ram_mb=0)
        assert result is None
        result2 = check_resources(min_disk_mb=10**9)  # absurdly high -> refusal message
        assert result2 is not None and "disk" in result2

    def test_request_cancel_sets_flag(self, app_env):
        # job_manager uses the app-level session store — the test must too.
        from app.api.job_manager import job_manager
        from app.db.engine import session_scope
        from app.db.models import JobRecord

        with session_scope() as session:
            session.add(
                JobRecord(
                    id="cancel-me",
                    type="collect-data",
                    status="running",
                    params_json="{}",
                    progress=0.0,
                    message="",
                )
            )
        assert job_manager._cancel_requested("cancel-me") is False
        assert job_manager.request_cancel("cancel-me") is True
        assert job_manager._cancel_requested("cancel-me") is True
