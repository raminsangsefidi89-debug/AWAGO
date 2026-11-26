"""Forecast and indicator endpoints (slug + BASE/QUOTE path shapes)."""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.errors import DataUnavailableError
from app.api.params import normalize_pair, pair_or_404
from app.db.engine import get_db
from app.schemas.forecast import ForecastResponse, IndicatorResponse, TrendResponse
from app.services.forecasting.inference import ModelNotFoundError, forecast_pair
from app.services.market import get_history
from app.services.trend import analyze_trend

from app.api.errors import ModelNotFoundErrorAPI

router = APIRouter(tags=["forecasting"])


# ------------------------------------------------------------------
# Forecast
# ------------------------------------------------------------------

def _forecast_response(symbol: str, horizon: int, db: Session) -> ForecastResponse:
    pair_or_404(db, symbol)
    try:
        result = forecast_pair(db, symbol, horizon)
    except ModelNotFoundError as exc:
        raise ModelNotFoundErrorAPI(str(exc)) from exc
    return ForecastResponse(**result)


@router.get(
    "/pairs/{pair}/forecast",
    response_model=ForecastResponse,
    summary="Point forecast with prediction interval (slug)",
)
def get_forecast(
    pair: str,
    horizon: int = Query(7, ge=1, le=365, description="Forecast horizon in calendar/trading days."),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    """Forecast the future close for one horizon using the trained model.

    Requires a previously trained model (launcher, CLI or POST /jobs/train).
    The interval is calibrated from walk-forward residuals.
    """
    return _forecast_response(normalize_pair(pair), horizon, db)


@router.get(
    "/pairs/{base}/{quote}/forecast",
    response_model=ForecastResponse,
    summary="Point forecast (BASE/QUOTE)",
    include_in_schema=False,
)
def get_forecast_split(
    base: str,
    quote: str,
    horizon: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    return _forecast_response(normalize_pair(f"{base}/{quote}"), horizon, db)


# ------------------------------------------------------------------
# Indicators
# ------------------------------------------------------------------

def _indicator_response(symbol: str, db: Session) -> IndicatorResponse:
    pair_or_404(db, symbol)
    bars = get_history(db, symbol)
    if len(bars) < 5:
        raise DataUnavailableError(f"Not enough history for {symbol} to compute indicators.")
    df = pd.DataFrame(
        {
            "timestamp": [b.timestamp for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
        }
    )
    trend = analyze_trend(df)
    return IndicatorResponse(
        pair_symbol=symbol,
        timestamp=bars[-1].timestamp.isoformat(),
        data_source=bars[-1].data_source,
        is_demo=bars[-1].is_demo,
        trend=TrendResponse(**trend),
    )


@router.get(
    "/pairs/{pair}/indicators",
    response_model=IndicatorResponse,
    summary="Technical indicators and trend analysis (slug)",
)
def get_indicators(pair: str, db: Session = Depends(get_db)) -> IndicatorResponse:
    """Latest indicator values (RSI, MACD, SMA, ATR, volatility) plus trend analysis."""
    return _indicator_response(normalize_pair(pair), db)


@router.get(
    "/pairs/{base}/{quote}/indicators",
    response_model=IndicatorResponse,
    summary="Technical indicators (BASE/QUOTE)",
    include_in_schema=False,
)
def get_indicators_split(base: str, quote: str, db: Session = Depends(get_db)) -> IndicatorResponse:
    return _indicator_response(normalize_pair(f"{base}/{quote}"), db)
