"""Model plugin registry with honest availability reporting."""

from __future__ import annotations

from app.logging_config import get_logger
from app.services.models.base import ForecastModel, ModelSpec
from app.services.models.baselines import (
    DriftModel,
    ETSModel,
    MovingAverageModel,
    NaiveModel,
    SeasonalNaiveModel,
)
from app.services.models.ml import (
    ElasticNetModel,
    ExtraTreesModel,
    HistGBModel,
    MLPModel,
    RandomForestModel,
    RecursiveRidgeModel,
    RidgeModel,
)
from app.services.models.probabilistic import QuantileGBM
from app.services.models.statistical import HAS_ARCH, ARIMAModel, GARCHModel

logger = get_logger(__name__)


def _spec(cls, description: str, available: bool = True, reason: str = "") -> ModelSpec:
    return ModelSpec(
        name=cls.name,
        kind=cls.kind,
        factory=cls,
        description=description,
        available=available,
        unavailable_reason=reason,
    )


_REGISTRY: list[ModelSpec] = [
    _spec(NaiveModel, "Random walk (expected return 0) — the honest yardstick"),
    _spec(DriftModel, "Average past h-step return (drift)"),
    _spec(SeasonalNaiveModel, "Weekly seasonal naive (same as 7 days ago)"),
    _spec(MovingAverageModel, "Forecast price = rolling mean of closes"),
    _spec(ETSModel, "Holt linear exponential smoothing (sequential walk-forward)"),
    _spec(ARIMAModel, "ARIMA(1,1,1) with bounded refit cadence (statsmodels)"),
    _spec(
        GARCHModel,
        "GARCH(1,1) volatility forecaster (direction forecast is 0 by design)",
        available=HAS_ARCH,
        reason="" if HAS_ARCH else "optional package 'arch' not installed (requirements-ml.txt)",
    ),
    _spec(RidgeModel, "Ridge regression, direct multi-horizon"),
    _spec(ElasticNetModel, "ElasticNet regression, direct multi-horizon"),
    _spec(RandomForestModel, "Random forest, direct multi-horizon"),
    _spec(ExtraTreesModel, "Extra trees, direct multi-horizon"),
    _spec(HistGBModel, "Histogram gradient boosting, direct multi-horizon"),
    _spec(MLPModel, "Small CPU MLP (deep-learning lite; no torch)"),
    _spec(RecursiveRidgeModel, "Recursive strategy: chained 1-step Ridge models"),
    _spec(QuantileGBM, "Quantile regression (GBM quantile loss) for intervals"),
]


def get_model(name: str, horizon: int = 1, **params) -> ForecastModel:
    for spec in _REGISTRY:
        if spec.name == name:
            if not spec.available:
                raise RuntimeError(f"Model '{name}' unavailable: {spec.unavailable_reason}")
            return spec.factory(horizon=horizon, **params)
    raise ValueError(f"Unknown model: {name!r}")


def available_models() -> list[dict]:
    return [spec.as_dict() for spec in _REGISTRY]


def core_model_names() -> list[str]:
    """Models used in the standard experiment (lite-safe subset)."""
    return [
        "baseline_naive",
        "baseline_drift",
        "baseline_seasonal_naive",
        "baseline_ma",
        "baseline_ets",
        "stat_arima",
        "ml_ridge",
        "ml_elasticnet",
        "ml_rf",
        "ml_extratrees",
        "ml_histgb",
        "deep_mlp",
        "ml_ridge_recursive",
    ]


def probabilistic_model_names() -> list[str]:
    return ["prob_quantile_gbm"]
