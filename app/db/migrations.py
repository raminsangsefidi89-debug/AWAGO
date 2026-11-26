"""Safe, automatic schema migrations on startup (Alembic).

Policy:

* fresh database            -> ``upgrade head``
* legacy v1 database        -> ``stamp 0001`` then ``upgrade head``
  (v1 created exactly the 0001 schema via create_all)
* already-versioned database -> ``upgrade head``

Existing data is always preserved. Migrations are idempotent.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from alembic import command
from app.config import get_settings
from app.db.engine import get_engine
from app.logging_config import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
V1_TABLES = {"currency_pairs", "price_bars", "model_artifacts", "metric_records", "job_records"}


def _alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().effective_database_url)
    return cfg


def _current_revision(connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def stamp_head() -> None:
    """Mark the database as up-to-date without running migrations."""
    command.stamp(_alembic_config(), "head")


def run_migrations() -> None:
    """Bring the schema to the latest revision, preserving data."""
    engine = get_engine()
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    cfg = _alembic_config()
    script = ScriptDirectory.from_config(cfg)

    with engine.connect() as connection:
        current = _current_revision(connection)

    if current is not None:
        # Already versioned: apply pending upgrades.
        head = script.get_current_head()
        if current != head:
            logger.info("Applying migrations %s -> %s", current, head)
            command.upgrade(cfg, "head")
        return

    if existing & V1_TABLES:
        # Legacy v1 database (created via create_all): stamp the initial
        # revision, then apply any v2 migrations on top.
        logger.info("Legacy v1 database detected — stamping revision 0001")
        command.stamp(cfg, "0001")
        head = script.get_current_head()
        if head != "0001":
            command.upgrade(cfg, "head")
        return

    # Fresh database.
    logger.info("Fresh database — creating schema via migrations")
    command.upgrade(cfg, "head")


def schema_version() -> str | None:
    """Current schema revision (for /health and diagnostics)."""
    engine = get_engine()
    with engine.connect() as connection:
        return _current_revision(connection)
