#!/usr/bin/env python3
"""Train forecasting models with walk-forward evaluation.

Training only happens here (or via the dashboard / POST /jobs/train) — never
automatically during server startup. Models are persisted under data/models/
with full metadata; every model is compared to the naive baseline.

Examples
--------
    python scripts/train_models.py
    python scripts/train_models.py --pairs EUR/USD --horizons 1,7
    python scripts/train_models.py --quick
"""

from __future__ import annotations

import argparse
import json

from common import bootstrap

bootstrap()

from app.config import get_settings  # noqa: E402
from app.db.engine import init_db, session_scope  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.services.forecasting.training import train_pair  # noqa: E402
from app.services.market import validate_pair_symbol  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pairs", type=str, default=None, help="Comma-separated pairs (default: all).")
    parser.add_argument("--horizons", type=str, default=None, help="Comma-separated horizons in days (default: all).")
    parser.add_argument("--quick", action="store_true", help="Reduced configuration for a fast run.")
    parser.add_argument("--list", action="store_true", help="List trained models and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    setup_logging(settings.logs_dir, settings.log_level)
    init_db()

    if args.list:
        from sqlalchemy import select

        from app.db.engine import session_scope as scope
        from app.db.models import ModelArtifact

        with scope() as session:
            rows = list(session.scalars(select(ModelArtifact)).all())
        if not rows:
            print("No trained models yet.")
        for r in rows:
            print(f"  {r.pair_symbol:8s} h={r.horizon:<3d} model={r.model_name:12s} "
                  f"rows={r.n_rows} source={r.data_source} trained_at={r.trained_at}")
        return 0

    pairs = [validate_pair_symbol(p) for p in args.pairs.split(",")] if args.pairs else list(settings.pairs_list)
    horizons = sorted({int(h) for h in args.horizons.split(",")}) if args.horizons else settings.horizons_list

    def progress(frac: float, msg: str) -> None:
        print(f"  [{frac:5.1%}] {msg}")

    failures = 0
    for pair in pairs:
        print(f"\n=== Training {pair} (horizons={horizons}, quick={args.quick}) ===")
        try:
            with session_scope() as session:
                result = train_pair(session, pair, horizons=horizons, settings=settings,
                                    quick=args.quick, progress=progress)
            for h, info in result["horizons"].items():
                met = info["metrics"]
                beats = "BEATS baseline" if met.get("beats_baseline") else "does NOT beat baseline"
                print(f"    h={h}: winner={info['winner']} MAE={met['mae']:.6f} "
                      f"(naive MAE={info['baselines']['naive']['mae']:.6f}) -> {beats}")
        except Exception as exc:  # noqa: BLE001 — CLI-friendly error
            failures += 1
            print(f"    ERROR: {exc}")

    print("\nDone." if failures == 0 else f"\nDone with {failures} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
