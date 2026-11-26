"""AWAGO CLI: config inspection, database migrations, reproducibility helpers.

Usage::

    python -m app.cli config show        # print settings with secrets redacted
    python -m app.cli config hash        # print the config hash
    python -m app.cli db upgrade         # run pending Alembic migrations
    python -m app.cli db stamp           # mark a legacy v1 DB as current
    python -m app.cli repro snapshot     # print the data-snapshot hash
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cmd_config_show(_args: argparse.Namespace) -> int:
    from app.config import get_settings

    print(json.dumps(get_settings().redacted_dict(), indent=2, default=str))
    return 0


def _cmd_config_hash(_args: argparse.Namespace) -> int:
    from app.config import get_settings

    print(get_settings().config_hash())
    return 0


def _cmd_db_upgrade(_args: argparse.Namespace) -> int:
    from app.db.migrations import run_migrations

    run_migrations()
    print("Database schema is up to date.")
    return 0


def _cmd_db_stamp(_args: argparse.Namespace) -> int:
    from app.db.migrations import stamp_head

    stamp_head()
    print("Database stamped at head (no schema changes applied).")
    return 0


def _cmd_repro_snapshot(_args: argparse.Namespace) -> int:
    from sqlalchemy import select

    from app.db.engine import session_scope
    from app.db.models import PriceBar
    from app.repro import snapshot_hash

    with session_scope() as session:
        rows = [
            (b.pair_symbol, b.timestamp.isoformat(), b.close, b.data_source)
            for b in session.scalars(select(PriceBar)).all()
        ]
    print(snapshot_hash(rows))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="AWAGO maintenance CLI")
    sub = parser.add_subparsers(dest="group", required=True)

    cfg = sub.add_parser("config", help="configuration utilities")
    cfg_sub = cfg.add_subparsers(dest="action", required=True)
    cfg_sub.add_parser("show", help="print all settings with secrets redacted")
    cfg_sub.add_parser("hash", help="print the deterministic config hash")

    db = sub.add_parser("db", help="database migrations")
    db_sub = db.add_subparsers(dest="action", required=True)
    db_sub.add_parser("upgrade", help="run pending Alembic migrations")
    db_sub.add_parser("stamp", help="stamp a legacy v1 database at head")

    repro = sub.add_parser("repro", help="reproducibility helpers")
    repro_sub = repro.add_subparsers(dest="action", required=True)
    repro_sub.add_parser("snapshot", help="print the data-snapshot hash")

    return parser


def _cmd_report(args: argparse.Namespace) -> int:
    from app.services.report.generator import generate_report

    html = generate_report(args.run)
    if args.out:
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"Report written to {args.out}")
    else:
        print(html)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        ("config", "show"): _cmd_config_show,
        ("config", "hash"): _cmd_config_hash,
        ("db", "upgrade"): _cmd_db_upgrade,
        ("db", "stamp"): _cmd_db_stamp,
        ("repro", "snapshot"): _cmd_repro_snapshot,
    }
    handler = handlers.get((args.group, args.action))
    if handler is None:
        print(f"Unknown command: {args.group} {args.action}", file=sys.stderr)
        return 2
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
