"""Data-quality and provider-status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.params import normalize_pair
from app.db.engine import get_db
from app.services.data_providers.factory import all_capabilities, provider_health
from app.services.quality import latest_report, run_quality_check

router = APIRouter(tags=["data-quality"])


@router.get("/quality/{pair}", summary="Data-quality report for a pair (slug)")
def get_quality(
    pair: str,
    refresh: bool = Query(
        False, description="Run a fresh check instead of returning the stored report."
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Return (or freshly run) the data-quality report: gaps, staleness,
    outliers, OHLC validity, and cross-rate consistency where applicable."""
    symbol = normalize_pair(pair)
    if not refresh:
        stored = latest_report(db, symbol)
        if stored is not None:
            return stored
    return run_quality_check(db, symbol)


@router.get(
    "/quality/{base}/{quote}", summary="Data-quality report (BASE/QUOTE)", include_in_schema=False
)
def get_quality_split(
    base: str, quote: str, refresh: bool = False, db: Session = Depends(get_db)
) -> dict:
    symbol = normalize_pair(f"{base}/{quote}")
    if not refresh:
        stored = latest_report(db, symbol)
        if stored is not None:
            return stored
    return run_quality_check(db, symbol)


@router.get("/providers", summary="Data-provider capabilities and health")
def get_providers() -> dict:
    """Declared capabilities of every provider (pairs, limits, license notes,
    whether the endpoint was ever verified live) plus a health check."""
    from app.config import get_settings

    settings = get_settings()
    return {
        "providers": all_capabilities(),
        "health": provider_health(settings),
        "note": (
            "Providers with verified_live=false could not be called from the "
            "build environment; treat them as unverified until you confirm "
            "them in your own network."
        ),
    }
