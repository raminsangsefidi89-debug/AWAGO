"""Forecast, indicator, model and metric schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    model_name: str = Field(..., description="Winning algorithm, e.g. 'ridge', 'hist_gb', 'lightgbm'.")
    trained_at: Optional[str] = None
    features_version: Optional[str] = None
    n_training_rows: Optional[int] = None
    beats_baseline: Optional[bool] = Field(
        None, description="True only when walk-forward MAE beats the naive baseline."
    )
    mae: Optional[float] = None
    smape: Optional[float] = None


class ForecastResponse(BaseModel):
    pair_symbol: str
    horizon_days: int
    forecast_price: float = Field(..., description="Point forecast of the future close.")
    forecast_log_return: float
    interval_lower: float = Field(..., description="Lower bound of the prediction interval.")
    interval_upper: float = Field(..., description="Upper bound of the prediction interval.")
    interval_level: float = Field(..., description="Interval width, e.g. 0.90 for 90%.")
    interval_method: str
    last_price: float
    last_data_timestamp: str = Field(..., description="Timestamp of the newest data point used.")
    forecast_target_date: str = Field(..., description="Approximate target date (calendar days).")
    data_source: str
    is_demo: bool
    model: ModelInfo
    disclaimer: str = Field(
        default="For educational and analytical purposes only. This is not financial advice.",
        description="Mandatory disclaimer.",
    )


class TrendResponse(BaseModel):
    direction: str = Field(..., description="'up' | 'down' | 'sideways'.")
    strength: float = Field(..., description="0-100 trend strength score.")
    slope_per_day: Optional[float] = None
    r_squared: Optional[float] = None
    lookback_bars: int
    volatility_regime: str = Field(..., description="'low' | 'medium' | 'high'.")
    volatility_percentile: Optional[float] = None
    indicators: Dict[str, Any]


class IndicatorResponse(BaseModel):
    pair_symbol: str
    timestamp: str = Field(..., description="Timestamp of the latest bar used.")
    data_source: str
    is_demo: bool
    trend: TrendResponse
