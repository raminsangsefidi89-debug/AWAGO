"""Currency pair, current price and history endpoints.

Each endpoint is registered in two shapes so that the natural pair form
``EUR/USD`` works inside the URL path:
    /pairs/{pair}/...        (slug: EURUSD, EUR-USD)
    /pairs/{base}/{quote}/... (natural: EUR/USD)
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.errors import BadRequestError, DataUnavailableError
from app.api.params import normalize_pair, pair_or_404
from app.db.engine import get_db
from app.schemas.market import (
    HistoryBar,
    HistoryResponse,
    PairInfo,
    PairListResponse,
    PriceResponse,
)
from app.services.market import (
    get_history,
    get_latest_bar,
    get_previous_bar,
    pairs_overview,
)

router = APIRouter(tags=["market"])

VALID_INTERVALS = {"1d"}


# ------------------------------------------------------------------
# Pairs
# ------------------------------------------------------------------


@router.get("/pairs", response_model=PairListResponse, summary="Available currency pairs")
def list_pairs(db: Session = Depends(get_db)) -> PairListResponse:
    """List all active currency pairs with their latest price and data source."""
    items = []
    for pair, bar in pairs_overview(db):
        items.append(
            PairInfo(
                symbol=pair.symbol,
                base=pair.base,
                quote=pair.quote,
                display_name_fa=pair.display_name_fa,
                is_active=pair.is_active,
                latest_price=bar.close if bar else None,
                latest_timestamp=bar.timestamp.isoformat() if bar else None,
                data_source=bar.data_source if bar else None,
                is_demo=bar.is_demo if bar else None,
            )
        )
    return PairListResponse(pairs=items, count=len(items))


# ------------------------------------------------------------------
# Current price
# ------------------------------------------------------------------


def _price_response(symbol: str, db: Session) -> PriceResponse:
    pair_or_404(db, symbol)
    bar = get_latest_bar(db, symbol)
    if bar is None:
        raise DataUnavailableError(
            f"No price data for {symbol} yet. Seed demo data or run data collection first."
        )
    prev = get_previous_bar(db, symbol)
    change_abs = change_pct = None
    if prev is not None and prev.close:
        change_abs = bar.close - prev.close
        change_pct = (bar.close / prev.close - 1.0) * 100.0
    return PriceResponse(
        pair_symbol=symbol,
        price=bar.close,
        timestamp=bar.timestamp.isoformat(),
        previous_close=prev.close if prev else None,
        change_abs=round(change_abs, 6) if change_abs is not None else None,
        change_pct=round(change_pct, 4) if change_pct is not None else None,
        interval=bar.interval,
        data_source=bar.data_source,
        is_demo=bar.is_demo,
    )


@router.get("/pairs/{pair}/price", response_model=PriceResponse, summary="Current price (slug)")
def current_price(pair: str, db: Session = Depends(get_db)) -> PriceResponse:
    """Latest price for a pair, with timestamp, source and change versus previous close."""
    return _price_response(normalize_pair(pair), db)


@router.get(
    "/pairs/{base}/{quote}/price",
    response_model=PriceResponse,
    summary="Current price (BASE/QUOTE)",
    include_in_schema=False,
)
def current_price_split(base: str, quote: str, db: Session = Depends(get_db)) -> PriceResponse:
    return _price_response(normalize_pair(f"{base}/{quote}"), db)


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------


def _history_response(
    symbol: str,
    db: Session,
    interval: str,
    start: datetime | None,
    end: datetime | None,
    limit: int,
) -> HistoryResponse:
    pair_or_404(db, symbol)
    if interval not in VALID_INTERVALS:
        raise BadRequestError(
            f"Unsupported interval {interval!r}; supported: {sorted(VALID_INTERVALS)}",
            code="invalid_interval",
        )
    bars = get_history(db, symbol, start=start, end=end, limit=limit)
    source = bars[-1].data_source if bars else "none"
    return HistoryResponse(
        pair_symbol=symbol,
        interval=interval,
        start=start.isoformat() if start else None,
        end=end.isoformat() if end else None,
        count=len(bars),
        data_source=source,
        is_demo=(source == "demo"),
        latest_timestamp=bars[-1].timestamp.isoformat() if bars else None,
        bars=[
            HistoryBar(
                timestamp=b.timestamp.isoformat(),
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
            )
            for b in bars
        ],
    )


@router.get(
    "/pairs/{pair}/history", response_model=HistoryResponse, summary="Historical prices (slug)"
)
def history(
    pair: str,
    interval: str = Query("1d", description="Bar interval. Only '1d' (daily) is supported."),
    start: datetime | None = Query(None, description="Inclusive start date (ISO)."),
    end: datetime | None = Query(None, description="Inclusive end date (ISO)."),
    limit: int = Query(500, ge=1, le=5000, description="Maximum number of bars returned."),
    db: Session = Depends(get_db),
) -> HistoryResponse:
    """Daily OHLC history for a pair (chronological order)."""
    return _history_response(normalize_pair(pair), db, interval, start, end, limit)


@router.get(
    "/pairs/{base}/{quote}/history",
    response_model=HistoryResponse,
    summary="Historical prices (BASE/QUOTE)",
    include_in_schema=False,
)
def history_split(
    base: str,
    quote: str,
    interval: str = Query("1d"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> HistoryResponse:
    return _history_response(normalize_pair(f"{base}/{quote}"), db, interval, start, end, limit)
