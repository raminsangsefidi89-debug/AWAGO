"""Market-data response schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PairInfo(BaseModel):
    symbol: str = Field(..., description="BASE/QUOTE, e.g. 'EUR/USD'.")
    base: str
    quote: str
    display_name_fa: str = Field(..., description="Persian display name.")
    is_active: bool
    latest_price: Optional[float] = Field(None, description="Most recent stored close.")
    latest_timestamp: Optional[str] = Field(None, description="ISO timestamp of the latest bar.")
    data_source: Optional[str] = Field(None, description="Source of the latest bar (e.g. 'demo', 'frankfurter').")
    is_demo: Optional[bool] = Field(None, description="True when the latest bar is synthetic demo data.")


class PairListResponse(BaseModel):
    pairs: List[PairInfo]
    count: int


class PriceResponse(BaseModel):
    pair_symbol: str
    price: float = Field(..., description="Latest close price.")
    timestamp: str = Field(..., description="ISO timestamp of the latest data point.")
    previous_close: Optional[float] = None
    change_abs: Optional[float] = Field(None, description="Change versus previous close.")
    change_pct: Optional[float] = Field(None, description="Percentage change versus previous close.")
    interval: str = "1d"
    data_source: str = Field(..., description="Name of the data source.")
    is_demo: bool = Field(..., description="True when this price is synthetic demo data.")


class HistoryBar(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class HistoryResponse(BaseModel):
    pair_symbol: str
    interval: str
    start: Optional[str] = None
    end: Optional[str] = None
    count: int
    data_source: str
    is_demo: bool
    latest_timestamp: Optional[str] = None
    bars: List[HistoryBar]
