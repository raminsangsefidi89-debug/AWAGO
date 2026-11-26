"""Model metadata and evaluation metric schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ModelArtifactInfo(BaseModel):
    pair_symbol: str
    horizon: int
    model_name: str
    trained_at: Optional[str] = None
    train_start: Optional[str] = None
    train_end: Optional[str] = None
    n_rows: int = 0
    features_version: str = "1"
    data_source: str = "demo"
    is_active: bool = True
    file_path: Optional[str] = Field(None, description="Path of the joblib bundle (server-side).")


class ModelListResponse(BaseModel):
    models: List[ModelArtifactInfo]
    count: int
    lightgbm_available: bool = Field(
        ..., description="Whether the optional LightGBM library is installed."
    )


class MetricItem(BaseModel):
    horizon: int
    model_name: str = Field(..., description="Model or baseline name ('naive', 'drift').")
    mae: float
    rmse: float
    smape: float
    mape: Optional[float] = None
    directional_accuracy: Optional[float] = Field(
        None,
        description="Percent of correctly predicted directions; null when the "
        "forecaster predicts no change (naive baseline).",
    )
    baseline_mae: float = Field(..., description="MAE of the naive baseline on identical test rows.")
    baseline_rmse: float
    beats_baseline: bool = Field(..., description="True when this model's MAE < naive baseline MAE.")
    n_test: int
    evaluated_at: Optional[str] = None
    data_source: str = "demo"


class MetricListResponse(BaseModel):
    pair_symbol: str
    metrics: List[MetricItem]
    disclaimer: str = "For educational and analytical purposes only. This is not financial advice."
