#!/usr/bin/env python3
"""Collect price history from the configured data provider.

Follows DATA_MODE from .env:
  demo -> deterministic synthetic data
  live -> real provider (Frankfurter / ECB rates)
  auto -> real provider with transparent demo fallback (if FALLBACK_TO_DEMO=true)

Examples
--------
    python scripts/collect_data.py
    python scripts/collect_data.py --pairs EUR/USD --days 365
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from common import bootstrap

bootstrap()

from app.config import get_settings  # noqa: E402
from app.db.engine import init_db, session_scope  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.services.market import collect_data, validate_pair_symbol  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pairs", type=str, default=None, help="Comma-separated pairs (default: all).")
    parser.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD.")
    parser.add_argument("--end", type=str, default=None, help="End date YYYY-MM-DD (default: today).")
    parser.add_argument("--days", type=int, default=None, help="Look-back window in days (default: HISTORY_DAYS).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    setup_logging(settings.logs_dir, settings.log_level)

    pairs = [validate_pair_symbol(p) for p in args.pairs.split(",")] if args.pairs else None
    end = date.fromisoformat(args.end) if args.end else date.today()
    if args.start:
        start = date.fromisoformat(args.start)
    else:
        start = end - timedelta(days=args.days or settings.history_days)

    init_db()
    try:
        with session_scope() as session:
            summary = collect_data(session, settings, pairs=pairs, start=start, end=end)
    except Exception as exc:  # noqa: BLE001 — CLI-friendly error
        print(f"ERROR: data collection failed: {exc}")
        print("Hint: set DATA_MODE=demo (or FALLBACK_TO_DEMO=true) in .env to work offline.")
        return 1

    print(json.dumps(summary, indent=2))
    if summary.get("fallback_used"):
        print("\nWARNING: the real data source was unreachable; DEMO data was stored instead "
              "(clearly flagged with is_demo=True).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
