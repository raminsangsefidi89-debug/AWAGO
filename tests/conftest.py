"""Shared pytest fixtures: isolated temp database, seeded demo data, TestClient."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session")
def temp_db_path(tmp_path_factory):
    return tmp_path_factory.mktemp("db") / "awago_test.db"


@pytest.fixture(scope="session")
def app_env(temp_db_path, monkeypatch_session):
    """Configure the environment BEFORE any settings/engine is built."""
    os.environ["DATABASE_URL"] = f"sqlite:///{temp_db_path}"
    os.environ["DATA_MODE"] = "demo"
    os.environ["DEMO_SEED"] = "42"
    os.environ["AUTO_TRAIN_ON_SEED"] = "false"
    os.environ["OPEN_BROWSER"] = "false"
    os.environ["LOG_LEVEL"] = "WARNING"

    from app.config import get_settings

    get_settings.cache_clear()

    from app.db.engine import init_db, reset_db_state

    reset_db_state()
    init_db()
    yield get_settings()
    reset_db_state()


class _MonkeyPatchSession:
    """Minimal placeholder so the fixture list reads naturally."""

    pass


@pytest.fixture(scope="session")
def monkeypatch_session():
    return _MonkeyPatchSession()


@pytest.fixture(scope="session")
def seeded_db(app_env):
    """Seed two pairs with deterministic demo history (one gets a trained model)."""
    from app.db.engine import session_scope
    from app.services.data_providers.demo import DemoProvider
    from app.services.market import ensure_pairs, upsert_bars

    settings = app_env
    provider = DemoProvider(seed=settings.demo_seed)
    end = date.today()
    start = end - timedelta(days=420)
    with session_scope() as session:
        ensure_pairs(session, settings)
        for symbol in ("EUR/USD", "USD/JPY"):
            bars = provider.fetch_history(symbol, start, end)
            upsert_bars(session, symbol, bars, data_source="demo")
    return settings


@pytest.fixture(scope="session")
def trained_db(seeded_db):
    """Train a small model for EUR/USD horizon 1 so forecast/metrics endpoints work."""
    from app.db.engine import session_scope
    from app.services.forecasting.training import train_pair

    settings = seeded_db
    with session_scope() as session:
        train_pair(session, "EUR/USD", horizons=[1], settings=settings, quick=True)
    return settings


@pytest.fixture(scope="session")
def client(trained_db):
    """TestClient against the fully seeded + trained app."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def tmp_session(tmp_path):
    """Isolated in-memory-style SQLite session for unit tests."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'unit.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()
