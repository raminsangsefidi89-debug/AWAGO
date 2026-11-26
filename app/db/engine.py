"""SQLAlchemy 2.x engine / session management (works with SQLite or PostgreSQL)."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def _build_engine() -> Engine:
    settings = get_settings()
    url = settings.effective_database_url
    kwargs: dict = {"future": True, "echo": False}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False, future=True
        )
    return _session_factory


def init_db() -> None:
    """Bring the schema to the latest revision (idempotent, data-preserving).

    Delegates to Alembic migrations (fresh DBs are created from migrations;
    legacy v1 databases are stamped and upgraded). Falls back to
    ``create_all`` if Alembic is unavailable for any reason.
    """
    try:
        from app.db.migrations import run_migrations

        run_migrations()
    except Exception:
        Base.metadata.create_all(get_engine())


def reset_db_state() -> None:
    """Dispose engine/session factory (used by tests to switch databases)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Transactional scope for scripts and background jobs."""
    session: Session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    session: Session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
