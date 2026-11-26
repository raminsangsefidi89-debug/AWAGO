#!/usr/bin/env python3
"""Seed the database with reproducible synthetic demo data.

The data generated here is unmistakably DEMO data (stored with
data_source='demo', is_demo=True) and is fully deterministic for a given
--seed. Use it to explore AWAGO offline or to prepare test data.

Examples
--------
    python scripts/seed_demo.py
    python scripts/seed_demo.py --pairs EUR/USD,USD/JPY --days 730 --seed 7
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from common import bootstrap

bootstrap()

from app.config import get_settings
from app.db.engine import init_db, session_scope
from app.logging_config import setup_logging
from app.services.data_providers.demo import DemoProvider
from app.services.market import ensure_pairs, upsert_bars, validate_pair_symbol


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--pairs",
        type=str,
        default=None,
        help="Comma-separated pairs (default: all configured pairs).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="How many calendar days of history to seed (default: HISTORY_DAYS).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for the synthetic walk (default: DEMO_SEED).",
    )
    parser.add_argument(
        "--end", type=str, default=None, help="Last day (YYYY-MM-DD, default: today)."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    setup_logging(settings.logs_dir, settings.log_level)

    pairs = (
        [validate_pair_symbol(p) for p in args.pairs.split(",")]
        if args.pairs
        else list(settings.pairs_list)
    )
    days = args.days or settings.history_days
    seed = args.seed if args.seed is not None else settings.demo_seed
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = end - timedelta(days=days)

    init_db()
    provider = DemoProvider(seed=seed)

    total_inserted = 0
    with session_scope() as session:
        ensure_pairs(session, settings)
        for symbol in pairs:
            bars = provider.fetch_history(symbol, start, end)
            inserted = upsert_bars(session, symbol, bars, data_source="demo")
            total_inserted += inserted
            print(f"  {symbol}: fetched={len(bars)} inserted={inserted}")

    print(
        f"\nSeeded demo data for {len(pairs)} pair(s), {total_inserted} new bars "
        f"({start.isoformat()} .. {end.isoformat()}, seed={seed})."
    )
    print("NOTE: this is synthetic DEMO data (is_demo=True), not real market data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
