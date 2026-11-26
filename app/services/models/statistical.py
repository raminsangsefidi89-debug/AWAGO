"""Statistical models: ARIMA (statsmodels) and GARCH (optional `arch`).

ARIMA refits on a cadence (``refit_every`` origins) over a bounded window
(``max_train``) for CPU budget honesty; between refits the latest fitted
model's h-step forecast is re-anchored to the current origin price.

GARCH predicts *volatility*, not direction: its point forecast is 0 (mean
equation), and it contributes a sigma forecast exposed via
``predict_sigma``. It is only available when the optional ``arch`` package
is installed (requirements-ml.txt); otherwise the registry marks it
unavailable with that exact reason.
"""

from __future__ import annotations

import numpy as np

from app.services.models.base import FitData, ForecastModel, PredictData

try:
    import arch

    HAS_ARCH = True
except Exception:
    arch = None
    HAS_ARCH = False


class ARIMAModel(ForecastModel):
    name = "stat_arima"
    kind = "statistical"

    def __init__(
        self,
        horizon: int = 1,
        order: tuple = (1, 1, 1),
        refit_every: int = 15,
        max_train: int = 500,
        **params,
    ) -> None:
        super().__init__(
            horizon, order=order, refit_every=refit_every, max_train=max_train, **params
        )
        self.order = order
        self.refit_every = refit_every
        self.max_train = max_train

    def _fit_on(self, prices: np.ndarray):
        from statsmodels.tsa.arima.model import ARIMA

        with np.errstate(all="ignore"):
            model = ARIMA(prices, order=self.order)
            return model.fit()

    def fit(self, data: FitData) -> ARIMAModel:
        prices = data.history.to_numpy(dtype=float)[-self.max_train :]
        try:
            self._result = self._fit_on(prices)
        except Exception:
            self._result = None
        return self

    def predict(self, data: PredictData) -> np.ndarray:
        hist = data.history.to_numpy(dtype=float)
        out = np.zeros(len(data))
        n_test = len(data)
        result = self._result
        for i in range(n_test):
            j = len(hist) - n_test + i
            if i % self.refit_every == 0:
                window = hist[max(0, j + 1 - self.max_train) : j + 1]
                try:
                    result = self._fit_on(window)
                except Exception:
                    result = None
            if result is not None:
                try:
                    price_f = float(np.asarray(result.forecast(self.horizon))[-1])
                    out[i] = float(np.log(price_f / hist[j])) if hist[j] and price_f > 0 else 0.0
                except Exception:
                    out[i] = 0.0
        self._result = result
        return out


class GARCHModel(ForecastModel):
    """GARCH(1,1) volatility forecaster (direction forecast = 0 by design)."""

    name = "stat_garch_vol"
    kind = "statistical"

    def fit(self, data: FitData) -> GARCHModel:
        if not HAS_ARCH:
            raise RuntimeError("package 'arch' is not installed (see requirements-ml.txt)")
        prices = data.history.to_numpy(dtype=float)
        rets = 100.0 * np.diff(np.log(prices))
        self._garch = arch.arch_model(rets, vol="GARCH", p=1, q=1, rescale=False).fit(disp="off")
        return self

    def predict(self, data: PredictData) -> np.ndarray:
        return np.zeros(len(data))

    def predict_sigma(self, horizon: int) -> float:
        """h-step-ahead conditional volatility (in return units)."""
        if not HAS_ARCH or not hasattr(self, "_garch"):
            return float("nan")
        forecasts = self._garch.forecast(horizon=horizon, reindex=False)
        var = float(forecasts.variance.to_numpy()[-1, -1])
        return float(np.sqrt(var) / 100.0)

    def predict_quantiles(
        self, data: PredictData, quantiles=(0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
    ):
        from scipy.stats import norm

        sigma = self.predict_sigma(self.horizon)
        if not np.isfinite(sigma):
            return None
        return {q: np.full(len(data), norm.ppf(q) * sigma) for q in quantiles}
