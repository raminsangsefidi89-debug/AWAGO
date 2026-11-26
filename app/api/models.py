"""Model metadata and evaluation-metric endpoints (slug + BASE/QUOTE shapes)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import NotFoundError
from app.api.params import normalize_pair
from app.db.engine import get_db
from app.db.models import MetricRecord, ModelArtifact
from app.schemas.models import MetricItem, MetricListResponse, ModelArtifactInfo, ModelListResponse
from app.services.forecasting.training import lightgbm_available

router = APIRouter(tags=["models"])


def _artifact_info(a: ModelArtifact) -> ModelArtifactInfo:
    return ModelArtifactInfo(
        pair_symbol=a.pair_symbol,
        horizon=a.horizon,
        model_name=a.model_name,
        trained_at=a.trained_at.isoformat() if a.trained_at else None,
        train_start=a.train_start.isoformat() if a.train_start else None,
        train_end=a.train_end.isoformat() if a.train_end else None,
        n_rows=a.n_rows,
        features_version=a.features_version,
        data_source=a.data_source,
        is_active=a.is_active,
        file_path=a.file_path,
    )


@router.get("/models", response_model=ModelListResponse, summary="All trained model artifacts")
def list_models(db: Session = Depends(get_db)) -> ModelListResponse:
    """List metadata for every persisted model (pair, horizon, training window, metrics)."""
    rows = list(
        db.scalars(select(ModelArtifact).order_by(ModelArtifact.pair_symbol, ModelArtifact.horizon)).all()
    )
    return ModelListResponse(
        models=[_artifact_info(a) for a in rows],
        count=len(rows),
        lightgbm_available=lightgbm_available(),
    )


def _models_for_pair(symbol: str, db: Session) -> ModelListResponse:
    rows = list(
        db.scalars(
            select(ModelArtifact)
            .where(ModelArtifact.pair_symbol == symbol)
            .order_by(ModelArtifact.horizon)
        ).all()
    )
    return ModelListResponse(
        models=[_artifact_info(a) for a in rows],
        count=len(rows),
        lightgbm_available=lightgbm_available(),
    )


@router.get(
    "/models/{pair}",
    response_model=ModelListResponse,
    summary="Trained models for one pair (slug)",
)
def list_models_for_pair(pair: str, db: Session = Depends(get_db)) -> ModelListResponse:
    """Model metadata for a single pair."""
    return _models_for_pair(normalize_pair(pair), db)


@router.get(
    "/models/{base}/{quote}",
    response_model=ModelListResponse,
    summary="Trained models for one pair (BASE/QUOTE)",
    include_in_schema=False,
)
def list_models_for_pair_split(base: str, quote: str, db: Session = Depends(get_db)) -> ModelListResponse:
    return _models_for_pair(normalize_pair(f"{base}/{quote}"), db)


def _metrics_for_pair(symbol: str, db: Session) -> MetricListResponse:
    rows = list(
        db.scalars(
            select(MetricRecord)
            .where(MetricRecord.pair_symbol == symbol)
            .order_by(MetricRecord.horizon, MetricRecord.mae)
        ).all()
    )
    if not rows:
        raise NotFoundError(
            f"No evaluation metrics for {symbol} yet. Train models first.",
            code="metrics_not_found",
        )
    items = []
    for r in rows:
        details = {}
        try:
            details = json.loads(r.details_json or "{}")
        except ValueError:
            details = {}
        items.append(
            MetricItem(
                horizon=r.horizon,
                model_name=r.model_name,
                mae=r.mae,
                rmse=r.rmse,
                smape=r.smape,
                mape=details.get("mape"),
                directional_accuracy=None if r.directional_accuracy < 0 else r.directional_accuracy,
                baseline_mae=r.baseline_mae,
                baseline_rmse=r.baseline_rmse,
                beats_baseline=r.beats_baseline,
                n_test=r.n_test,
                evaluated_at=r.evaluated_at.isoformat() if r.evaluated_at else None,
                data_source=r.data_source,
            )
        )
    return MetricListResponse(pair_symbol=symbol, metrics=items)


@router.get(
    "/metrics/{pair}",
    response_model=MetricListResponse,
    summary="Walk-forward metrics with baseline comparison (slug)",
)
def get_metrics(pair: str, db: Session = Depends(get_db)) -> MetricListResponse:
    """Evaluation metrics per horizon for every model and baseline.

    Each item reports MAE/RMSE/sMAPE/Directional Accuracy and whether the
    model honestly beats the naive baseline on identical walk-forward test rows.
    """
    return _metrics_for_pair(normalize_pair(pair), db)


@router.get(
    "/metrics/{base}/{quote}",
    response_model=MetricListResponse,
    summary="Walk-forward metrics (BASE/QUOTE)",
    include_in_schema=False,
)
def get_metrics_split(base: str, quote: str, db: Session = Depends(get_db)) -> MetricListResponse:
    return _metrics_for_pair(normalize_pair(f"{base}/{quote}"), db)
