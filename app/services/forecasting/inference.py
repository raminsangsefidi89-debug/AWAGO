"""Forecast generation from persisted models (no training on request)."""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Dict, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import ModelArtifact
from app.logging_config import get_logger
from app.services.features import build_feature_frame, feature_columns
from app.services.forecasting.persistence import load_bundle
from app.services.market import get_history

logger = get_logger(__name__)


class ModelNotFoundError(RuntimeError):
    """No trained model exists for the requested pair/horizon/source."""


def find_artifact(
    session: Session, pair_symbol: str, horizon: int, data_source: Optional[str] = None
) -> Optional[ModelArtifact]:
    stmt = select(ModelArtifact).where(
        ModelArtifact.pair_symbol == pair_symbol,
        ModelArtifact.horizon == horizon,
        ModelArtifact.is_active.is_(True),
    )
    if data_source:
        stmt = stmt.where(ModelArtifact.data_source == data_source)
    stmt = stmt.order_by(ModelArtifact.trained_at.desc()).limit(1)
    return session.scalars(stmt).first()


def forecast_pair(
    session: Session,
    pair_symbol: str,
    horizon: int,
    settings: Optional[Settings] = None,
) -> Dict:
    """Produce a point forecast with prediction interval for one pair/horizon.

    The model must have been trained beforehand (launcher/CLI/API job).
    Raises ModelNotFoundError when no matching artifact exists.
    """
    settings = settings or get_settings()

    bars = get_history(session, pair_symbol)
    if len(bars) < 60:
        raise ModelNotFoundError(
            f"Not enough history for {pair_symbol} ({len(bars)} bars); collect data first."
        )
    data_source = bars[-1].data_source

    artifact = find_artifact(session, pair_symbol, horizon, data_source)
    if artifact is None:
        raise ModelNotFoundError(
            f"No trained model for {pair_symbol} horizon={horizon} days on source "
            f"'{data_source}'. Train models first (dashboard button, CLI scripts/train_models.py, "
            "or POST /api/v1/jobs/train)."
        )

    bundle = load_bundle(artifact.file_path)
    model = bundle["model"]

    df = pd.DataFrame(
        {
            "timestamp": [b.timestamp for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
        }
    )
    frame = build_feature_frame(df, [horizon])
    feats = bundle.get("feature_cols") or feature_columns()
    last = frame.iloc[-1]
    if last[feats].isna().any():
        raise ModelNotFoundError(
            f"Latest rows for {pair_symbol} still in feature warm-up; need more history."
        )

    X_last = last[feats].to_numpy(dtype=float).reshape(1, -1)
    pred_logret = float(model.predict(X_last)[0])
    last_close = float(last["close"])
    pred_price = last_close * math.exp(pred_logret)

    q_lo = float(bundle.get("resid_q_lo", 0.0))
    q_hi = float(bundle.get("resid_q_hi", 0.0))
    level = float(bundle.get("interval_level", settings.prediction_interval_level))
    lower = last_close * math.exp(pred_logret + q_lo)
    upper = last_close * math.exp(pred_logret + q_hi)

    last_ts = pd.to_datetime(df["timestamp"].iloc[-1])
    target_ts = last_ts + timedelta(days=horizon)

    metrics = bundle.get("metrics", {})
    return {
        "pair_symbol": pair_symbol,
        "horizon_days": horizon,
        "forecast_price": round(pred_price, 6),
        "forecast_log_return": round(pred_logret, 6),
        "interval_lower": round(lower, 6),
        "interval_upper": round(upper, 6),
        "interval_level": level,
        "interval_method": "empirical_quantiles_of_walk_forward_residuals",
        "last_price": round(last_close, 6),
        "last_data_timestamp": last_ts.isoformat(),
        "forecast_target_date": target_ts.date().isoformat(),
        "data_source": data_source,
        "is_demo": data_source == "demo",
        "model": {
            "model_name": bundle.get("model_name", artifact.model_name),
            "trained_at": bundle.get("trained_at", artifact.trained_at.isoformat()),
            "features_version": bundle.get("features_version", artifact.features_version),
            "n_training_rows": bundle.get("n_rows", artifact.n_rows),
            "beats_baseline": metrics.get("beats_baseline"),
            "mae": metrics.get("mae"),
            "smape": metrics.get("smape"),
        },
    }
