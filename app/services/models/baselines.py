"""Baseline models — the honest yardstick every serious model must beat.

All baselines forecast the h-step future log return from price history only.
"""

from __future__ import annotations

import numpy as np

from app.services.models.base import FitData, ForecastModel, PredictData


class NaiveModel(ForecastModel):
    """Random walk: tomorrow equals today -> expected log return 0."""

    name = "baseline_naive"
    kind = "baseline"

    def fit(self, data: FitData) -> NaiveModel:
        return self

    def predict(self, data: PredictData) -> np.ndarray:
        return np.zeros(len(data))


class DriftModel(ForecastModel):
    """Average of the past h-step returns (drift of the random walk)."""

    name = "baseline_drift"
    kind = "baseline"

    def fit(self, data: FitData) -> DriftModel:
        h = self.horizon
        hist = data.history.to_numpy(dtype=float)
        if len(hist) > h:
            self._drift = float(np.mean(np.log(hist[h:] / hist[:-h])))
        else:
            self._drift = 0.0
        return self

    def predict(self, data: PredictData) -> np.ndarray:
        drift = getattr(self, "_drift", 0.0)
        return np.full(len(data), drift)


class SeasonalNaiveModel(ForecastModel):
    """Same as 7 days ago (weekly seasonality in daily FX)."""

    name = "baseline_seasonal_naive"
    kind = "baseline"
    season = 7

    def fit(self, data: FitData) -> SeasonalNaiveModel:
        return self

    def predict(self, data: PredictData) -> np.ndarray:
        hist = data.history.to_numpy(dtype=float)
        out = np.zeros(len(data))
        for i in range(len(data)):
            j = len(data.history) - len(data) + i  # origin index in history
            if j - self.season >= 0:
                out[i] = np.log(hist[j] / hist[j - self.season])
            # h-step from 7d ago is approximated by the 7d return; honest label below
        return out


class MovingAverageModel(ForecastModel):
    """Forecast price = mean of last w closes -> implied h-step log return."""

    name = "baseline_ma"
    kind = "baseline"

    def __init__(self, horizon: int = 1, window: int = 20, **params) -> None:
        super().__init__(horizon, window=window, **params)
        self.window = window

    def fit(self, data: FitData) -> MovingAverageModel:
        return self

    def predict(self, data: PredictData) -> np.ndarray:
        hist = data.history.to_numpy(dtype=float)
        out = np.zeros(len(data))
        for i in range(len(data)):
            j = len(data.history) - len(data) + i
            lo = max(0, j - self.window + 1)
            out[i] = np.log(float(np.mean(hist[lo : j + 1])) / hist[j])
        return out


class ETSModel(ForecastModel):
    """Holt's linear exponential smoothing (ETS(A,A,N)) on log prices.

    Sequential walk-forward: the level/trend state is updated with each
    observed close as test origins arrive (no per-origin refit, no stale
    forecasts). Damped trend optional via ``phi``.
    """

    name = "baseline_ets"
    kind = "statistical"

    def __init__(
        self, horizon: int = 1, alpha: float = 0.3, beta: float = 0.1, phi: float = 1.0, **params
    ) -> None:
        super().__init__(horizon, alpha=alpha, beta=beta, phi=phi, **params)
        self.alpha = alpha
        self.beta = beta
        self.phi = phi

    def fit(self, data: FitData) -> ETSModel:
        hist = np.log(data.history.to_numpy(dtype=float))
        if len(hist) < 2:
            self._level = float(hist[-1]) if len(hist) else 0.0
            self._trend = 0.0
            return self
        level = float(hist[0])
        trend = float(hist[1] - hist[0])
        for x in hist[1:]:
            prev_level = level
            level = self.alpha * x + (1.0 - self.alpha) * (level + self.phi * trend)
            trend = self.beta * (level - prev_level) + (1.0 - self.beta) * self.phi * trend
        self._level = level
        self._trend = trend
        return self

    def _forecast_log(self, h: int) -> float:
        level, trend, phi = self._level, self._trend, self.phi
        damp = sum(phi**j for j in range(1, h + 1))
        return float(level + trend * damp)

    def predict(self, data: PredictData) -> np.ndarray:
        hist = data.history.to_numpy(dtype=float)
        out = np.zeros(len(data))
        n_hist = len(hist)
        n_test = len(data)
        for i in range(n_test):
            j = n_hist - n_test + i
            log_origin = float(np.log(hist[j]))
            out[i] = self._forecast_log(self.horizon) - log_origin
            # update state with the observed close at this origin (available at T)
            x = float(np.log(hist[j]))
            prev_level = self._level
            self._level = self.alpha * x + (1.0 - self.alpha) * (
                self._level + self.phi * self._trend
            )
            self._trend = (
                self.beta * (self._level - prev_level) + (1.0 - self.beta) * self.phi * self._trend
            )
        return out


BASELINE_MODELS = [NaiveModel, DriftModel, SeasonalNaiveModel, MovingAverageModel, ETSModel]
