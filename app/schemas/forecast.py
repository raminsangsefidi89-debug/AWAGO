"""Forecast, indicator, model and metric schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    model_name: str = Field(
        ..., description="Winning algorithm, e.g. 'ridge', 'hist_gb', 'lightgbm'."
    )
    trained_at: str | None = None
    features_version: str | None = None
    n_training_rows: int | None = None
    beats_baseline: bool | None = Field(
        None, description="True only when walk-forward MAE beats the naive baseline."
    )
    mae: float | None = None
    smape: float | None = None


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
    slope_per_day: float | None = None
    r_squared: float | None = None
    lookback_bars: int
    volatility_regime: str = Field(..., description="'low' | 'medium' | 'high'.")
    volatility_percentile: float | None = None
    indicators: dict[str, Any]


class IndicatorResponse(BaseModel):
    pair_symbol: str
    timestamp: str = Field(..., description="Timestamp of the latest bar used.")
    data_source: str
    is_demo: bool
    trend: TrendResponse
