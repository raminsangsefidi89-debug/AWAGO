"""Probabilistic forecasting: quantile regression + conformal prediction.

Methods (P0 per spec):
* **Residual quantiles** — empirical quantiles of walk-forward residuals.
* **Split conformal** — time-aware split: calibrate on the tail of the train
  window, symmetric intervals from residual quantiles. Marginal coverage
  guarantee under exchangeability (which time series only approximate —
  reported honestly in every coverage table).
* **CQR (conformalized quantile regression)** — quantile model (GBM
  quantile loss) adjusted by conformalized quantile errors.
* **Adaptive conformal** — rolling window of the most recent calibration
  residuals (tracks slowly moving noise levels).

Every method reports *empirical* coverage vs *nominal* — never just the
nominal number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.services.models.base import DEFAULT_QUANTILES, FitData, ForecastModel, PredictData


@dataclass
class IntervalReport:
    method: str
    nominal_level: float
    empirical_coverage: float
    mean_width: float
    n: int

    def as_dict(self) -> dict:
        return {
            "method": self.method,
            "nominal_level": self.nominal_level,
            "empirical_coverage": self.empirical_coverage,
            "mean_width": self.mean_width,
            "n": self.n,
        }


def empirical_intervals(residuals: np.ndarray, nominal_level: float = 0.90) -> tuple[float, float]:
    """Symmetric interval half-width from empirical residual quantiles."""
    alpha = (1.0 - nominal_level) / 2.0
    lo = float(np.nanquantile(residuals, alpha))
    hi = float(np.nanquantile(residuals, 1.0 - alpha))
    return lo, hi


def split_conformal(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    nominal_level: float = 0.90,
    calib_fraction: float = 0.25,
) -> dict[str, np.ndarray]:
    """Time-aware split conformal: last ``calib_fraction`` calibrates."""
    n = len(y_true)
    n_calib = max(10, int(n * calib_fraction))
    if n <= n_calib + 5:
        n_calib = max(3, n // 4)
    np.abs(y_true[: n - n_calib] - y_pred[: n - n_calib])
    calib_residuals = np.abs(y_true[n - n_calib :] - y_pred[n - n_calib :])
    q = (
        float(np.quantile(calib_residuals, np.ceil((n_calib + 1) * nominal_level) / n_calib))
        if n_calib
        else 0.0
    )
    return {
        "lower": y_pred - q,
        "upper": y_pred + q,
        "q": np.full(n, q),
    }


def adaptive_conformal(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    nominal_level: float = 0.90,
    window: int = 50,
) -> dict[str, np.ndarray]:
    """Rolling-window conformal: q adapts using the latest residuals.

    Predicted intervals for row i use residuals observed strictly BEFORE i
    (the first ``window`` rows use expanding residuals), so no future
    information is used.
    """
    n = len(y_true)
    lower = np.zeros(n)
    upper = np.zeros(n)
    q_values = np.zeros(n)
    for i in range(n):
        lo = max(0, i - window)
        hist = np.abs(y_true[lo:i] - y_pred[lo:i])
        q = float(np.quantile(hist, nominal_level)) if len(hist) >= 5 else 0.0
        q_values[i] = q
        lower[i] = y_pred[i] - q
        upper[i] = y_pred[i] + q
    return {"lower": lower, "upper": upper, "q": q_values}


class QuantileGBM(ForecastModel):
    """Direct quantile regression via GradientBoosting per quantile."""

    name = "prob_quantile_gbm"
    kind = "ml"
    uses_features = True

    def __init__(
        self, horizon: int = 1, quantiles: tuple[float, ...] = (0.1, 0.5, 0.9), **params
    ) -> None:
        super().__init__(horizon, quantiles=quantiles, **params)
        self.quantiles = tuple(quantiles)

    @staticmethod
    def _X(features):
        X = features.drop(columns=["timestamp", "pair_symbol"], errors="ignore")
        X = X.select_dtypes(include=[np.number])
        return X.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def fit(self, data: FitData) -> QuantileGBM:
        from sklearn.ensemble import GradientBoostingRegressor

        X = self._X(data.features)
        y = data.target.to_numpy(dtype=float)
        self._models: dict[float, Any] = {}
        for q in self.quantiles:
            model = GradientBoostingRegressor(
                loss="quantile",
                alpha=q,
                n_estimators=80,
                max_depth=3,
                learning_rate=0.05,
                random_state=42,
            )
            model.fit(X, y)
            self._models[q] = model
        self._train_cols = list(X.columns)
        # median model doubles as the point forecast
        self._point = self._models.get(0.5) or next(iter(self._models.values()))
        return self

    def predict(self, data: PredictData) -> np.ndarray:
        X = self._X(data.features)[self._train_cols]
        return np.asarray(self._point.predict(X), dtype=float)

    def predict_quantiles(
        self, data: PredictData, quantiles: tuple[float, ...] = DEFAULT_QUANTILES
    ):
        X = self._X(data.features)[self._train_cols]
        out: dict[float, np.ndarray] = {}
        for q in quantiles:
            if q in self._models:
                out[q] = np.asarray(self._models[q].predict(X), dtype=float)
            else:
                # interpolate between fitted quantiles
                fitted = sorted(self._models)
                if len(fitted) >= 2:
                    lo = max([x for x in fitted if x <= q], default=fitted[0])
                    hi = min([x for x in fitted if x >= q], default=fitted[-1])
                    lo_pred = np.asarray(self._models[lo].predict(X), dtype=float)
                    hi_pred = np.asarray(self._models[hi].predict(X), dtype=float)
                    w = 0.0 if hi == lo else (q - lo) / (hi - lo)
                    out[q] = lo_pred * (1 - w) + hi_pred * w
        return out


def cqr_conformal(
    y_true: np.ndarray,
    q_lo_pred: np.ndarray,
    q_hi_pred: np.ndarray,
    nominal_level: float = 0.90,
    calib_fraction: float = 0.25,
) -> dict[str, np.ndarray]:
    """Conformalized quantile regression: adjust model quantiles by the
    conformal quantile of quantile errors (Romano et al., 2019)."""
    n = len(y_true)
    n_calib = max(10, int(n * calib_fraction))
    np.maximum(
        q_lo_pred[: n - n_calib] - y_true[: n - n_calib],
        y_true[: n - n_calib] - q_hi_pred[: n - n_calib],
    )
    calib_scores = np.maximum(
        q_lo_pred[n - n_calib :] - y_true[n - n_calib :],
        y_true[n - n_calib :] - q_hi_pred[n - n_calib :],
    )
    qhat = (
        float(np.quantile(calib_scores, np.ceil((n_calib + 1) * nominal_level) / n_calib))
        if n_calib
        else 0.0
    )
    return {"lower": q_lo_pred - qhat, "upper": q_hi_pred + qhat}


def coverage_report(
    y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray, method: str, nominal_level: float
) -> IntervalReport:
    y = np.asarray(y_true, dtype=float)
    covered = float(np.mean((y >= lower) & (y <= upper)))
    widths = upper - lower
    return IntervalReport(
        method=method,
        nominal_level=nominal_level,
        empirical_coverage=round(covered, 4),
        mean_width=round(float(np.nanmean(widths)), 6),
        n=len(y),
    )
