"""Model plugin interface: one contract for every forecasting model.

Every plugin predicts the *future log return* over ``horizon`` bars from
information available at each origin row (point-in-time). The harness feeds
aligned pandas objects; models never see test data during ``fit``.

``predict_quantiles`` is optional — probabilistic coverage is reported for
models that implement it, and honestly omitted for those that do not.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_QUANTILES: tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)


@dataclass
class FitData:
    """Aligned training slice. ``history`` is the close-price series."""

    pair_symbol: str
    horizon: int
    history: pd.Series  # close prices, indexed by timestamp (train rows only)
    features: pd.DataFrame  # feature rows aligned with history index
    target: pd.Series  # future log returns aligned with history index
    timestamps: pd.DatetimeIndex

    def __len__(self) -> int:
        return len(self.target)


@dataclass
class PredictData:
    """Prediction origins. ``history`` may extend beyond the train slice."""

    pair_symbol: str
    horizon: int
    history: pd.Series
    features: pd.DataFrame
    timestamps: pd.DatetimeIndex

    def __len__(self) -> int:
        return len(self.timestamps)


class ForecastModel(ABC):
    """Base class for all forecasting models."""

    name: str = "base"
    kind: str = "base"  # baseline | statistical | ml | deep | ensemble
    uses_features: bool = False
    optional_requires: tuple[str, ...] = ()  # modules that may be missing

    def __init__(self, horizon: int = 1, **params: Any) -> None:
        self.horizon = horizon
        self.params = params

    @abstractmethod
    def fit(self, data: FitData) -> ForecastModel: ...

    @abstractmethod
    def predict(self, data: PredictData) -> np.ndarray:
        """Point forecast of the h-step future log return, one per origin."""
        ...

    def predict_quantiles(
        self, data: PredictData, quantiles: tuple[float, ...] = DEFAULT_QUANTILES
    ) -> dict[float, np.ndarray] | None:
        """Optional quantile forecasts; None means 'not supported'."""
        return None

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps({"name": self.name, "horizon": self.horizon, "params": self.params}),
            encoding="utf-8",
        )

    def load(self, path: Path) -> ForecastModel:
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.horizon = int(doc.get("horizon", self.horizon))
        self.params = doc.get("params", {})
        return self

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "horizon": self.horizon,
            "uses_features": self.uses_features,
            "params": {k: str(v) for k, v in self.params.items()},
        }


@dataclass
class ModelSpec:
    """Registry entry: factory + honest availability info."""

    name: str
    kind: str
    factory: Any  # (horizon, **params) -> ForecastModel
    description: str = ""
    optional_requires: tuple[str, ...] = ()
    available: bool = True
    unavailable_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
        }
