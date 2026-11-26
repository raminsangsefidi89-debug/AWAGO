"""Data-quality service: run checks and persist reports."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PriceBar, QualityReport
from app.logging_config import get_logger
from app.services.quality.engine import build_quality_report

logger = get_logger(__name__)


def _bars_frame(session: Session, pair_symbol: str, data_source: str) -> pd.DataFrame:
    rows = list(
        session.scalars(
            select(PriceBar)
            .where(
                PriceBar.pair_symbol == pair_symbol,
                PriceBar.data_source == data_source,
                PriceBar.interval == "1d",
            )
            .order_by(PriceBar.timestamp)
        ).all()
    )
    return pd.DataFrame(
        {
            "timestamp": [b.timestamp for b in rows],
            "open": [b.open for b in rows],
            "high": [b.high for b in rows],
            "low": [b.low for b in rows],
            "close": [b.close for b in rows],
        }
    )


def run_quality_check(session: Session, pair_symbol: str, *, store: bool = True) -> dict[str, Any]:
    """Run the full quality suite for a pair's active series and store the report."""
    from app.services.market import get_active_source

    data_source = get_active_source(session, pair_symbol) or "demo"
    df = _bars_frame(session, pair_symbol, data_source)
    is_demo = data_source == "demo"

    cross_legs: dict[str, pd.DataFrame] | None = None
    if not is_demo:
        # Triangular check needs EUR/USD, GBP/USD, EUR/GBP from the same source.
        legs: dict[str, pd.DataFrame] = {}
        for leg in ("EUR/USD", "GBP/USD", "EUR/GBP"):
            leg_df = _bars_frame(session, leg, data_source)
            if len(leg_df) == 0:
                legs = {}
                break
            legs[leg] = leg_df
        cross_legs = legs or None

    report = build_quality_report(
        pair_symbol, data_source, df, is_demo=is_demo, cross_legs=cross_legs
    )
    if store:
        session.add(
            QualityReport(
                pair_symbol=pair_symbol,
                data_source=data_source,
                schema_version=report["schema_version"],
                status=report["summary"]["status"],
                issue_count=report["summary"]["issue_count"],
                report_json=json.dumps(report),
            )
        )
        session.commit()
    return report


def latest_report(session: Session, pair_symbol: str) -> dict[str, Any] | None:
    """Most recently stored report for a pair (or None)."""
    row = session.scalars(
        select(QualityReport)
        .where(QualityReport.pair_symbol == pair_symbol)
        .order_by(QualityReport.generated_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    try:
        return json.loads(row.report_json)
    except ValueError:
        return None
