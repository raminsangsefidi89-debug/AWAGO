"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.engine import get_db
from app.db.models import PriceBar
from app.schemas.common import HealthResponse

DISCLAIMER = "For educational and analytical purposes only. This is not financial advice."

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health and data status")
def health(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> HealthResponse:
    """Report service status, configured data mode, DB connectivity and latest data timestamp."""
    db_status = "connected"
    bar_count = 0
    latest_ts = None
    latest_source = None
    pair_count = 0
    try:
        from app.db.models import CurrencyPair

        pair_count = int(db.scalar(select(func.count(CurrencyPair.id))) or 0)
        bar_count = int(db.scalar(select(func.count(PriceBar.id))) or 0)
        row = db.execute(
            select(PriceBar.timestamp, PriceBar.data_source)
            .order_by(PriceBar.timestamp.desc())
            .limit(1)
        ).first()
        if row is not None:
            latest_ts = row[0].isoformat() if row[0] else None
            latest_source = row[1]
    except Exception:
        db_status = "error"

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        app_name=settings.app_name,
        version=settings.app_version,
        data_mode=settings.data_mode,
        database=db_status,
        pair_count=pair_count,
        price_bar_count=bar_count,
        latest_data_timestamp=latest_ts,
        latest_data_source=latest_source,
        disclaimer=DISCLAIMER,
    )
