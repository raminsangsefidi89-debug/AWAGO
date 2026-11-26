"""Classical ML models (direct multi-horizon) + a small MLP deep model.

Every model maps feature rows to the h-step future log return (direct
strategy: one model per horizon). The recursive strategy is available as a
separate plugin that chains 1-step models.

Heavy deep-learning frameworks (torch) are deliberately NOT required; the
``mlp`` plugin uses sklearn's CPU MLPRegressor and is honest about what it
is. TFT/PatchTST/LSTM remain documented skips (see ADR-0004).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.models.base import FitData, ForecastModel, PredictData


class _SklearnRegressorModel(ForecastModel):
    kind = "ml"
    uses_features = True

    def _build(self):
        raise NotImplementedError

    @staticmethod
    def _X(features) -> pd.DataFrame:

        X = features.drop(columns=["timestamp", "pair_symbol"], errors="ignore")
        X = X.select_dtypes(include=[np.number])
        return X.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def fit(self, data: FitData) -> _SklearnRegressorModel:
        self.model = self._build()
        X = self._X(data.features)
        y = data.target.to_numpy(dtype=float)
        self.model.fit(X, y)
        self._train_cols = list(X.columns)
        return self

    def predict(self, data: PredictData) -> np.ndarray:
        X = self._X(data.features)[self._train_cols]
        return np.asarray(self.model.predict(X), dtype=float)

    def save(self, path) -> None:
        import joblib

        joblib.dump({"model": self.model, "cols": self._train_cols, "horizon": self.horizon}, path)

    def load(self, path) -> _SklearnRegressorModel:
        import joblib

        doc = joblib.load(path)
        self.model = doc["model"]
        self._train_cols = doc["cols"]
        self.horizon = doc["horizon"]
        return self


class RidgeModel(_SklearnRegressorModel):
    name = "ml_ridge"

    def _build(self):
        from sklearn.linear_model import Ridge

        return Ridge(alpha=1.0)


class ElasticNetModel(_SklearnRegressorModel):
    name = "ml_elasticnet"

    def _build(self):
        from sklearn.linear_model import ElasticNet

        return ElasticNet(alpha=0.01, l1_ratio=0.5, max_iter=5000)


class RandomForestModel(_SklearnRegressorModel):
    name = "ml_rf"

    def __init__(self, horizon: int = 1, n_estimators: int = 100, **params) -> None:
        super().__init__(horizon, n_estimators=n_estimators, **params)
        self.n_estimators = n_estimators

    def _build(self):
        from sklearn.ensemble import RandomForestRegressor

        return RandomForestRegressor(
            n_estimators=self.n_estimators, min_samples_leaf=5, random_state=42, n_jobs=1
        )


class ExtraTreesModel(_SklearnRegressorModel):
    name = "ml_extratrees"

    def __init__(self, horizon: int = 1, n_estimators: int = 100, **params) -> None:
        super().__init__(horizon, n_estimators=n_estimators, **params)
        self.n_estimators = n_estimators

    def _build(self):
        from sklearn.ensemble import ExtraTreesRegressor

        return ExtraTreesRegressor(
            n_estimators=self.n_estimators, min_samples_leaf=5, random_state=42, n_jobs=1
        )


class HistGBModel(_SklearnRegressorModel):
    name = "ml_histgb"

    def _build(self):
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05, random_state=42)


class MLPModel(_SklearnRegressorModel):
    """Small CPU MLP (the 'deep learning lite' model; no torch required)."""

    name = "deep_mlp"
    kind = "deep"

    def _build(self):
        from sklearn.neural_network import MLPRegressor
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(
            StandardScaler(),
            MLPRegressor(
                hidden_layer_sizes=(32, 16), max_iter=300, early_stopping=True, random_state=42
            ),
        )


class RecursiveRidgeModel(ForecastModel):
    """Recursive strategy: chain 1-step Ridge models up to h."""

    name = "ml_ridge_recursive"
    kind = "ml"
    uses_features = True

    def fit(self, data: FitData) -> RecursiveRidgeModel:
        from sklearn.linear_model import Ridge

        self.models = []
        close = data.history.to_numpy(dtype=float)
        X = _SklearnRegressorModel._X(data.features)
        n = len(data)
        # step-k target: log return over (t, t+k]; only rows with enough future
        for k in range(1, self.horizon + 1):
            y_k = np.log(close[k:] / close[:-k]) if k < n else np.zeros(0)
            X_k = X.iloc[: len(y_k)]
            model = Ridge(alpha=1.0)
            if len(y_k) >= 30:
                model.fit(X_k, y_k)
            self.models.append(model)
        self._train_cols = list(X.columns)
        return self

    def predict(self, data: PredictData) -> np.ndarray:
        X = _SklearnRegressorModel._X(data.features)[self._train_cols]
        # approximate recursion: sum of per-step predictions scaled by 1/k correction
        out = np.zeros(len(data))
        for k, model in enumerate(self.models, start=1):
            out += np.asarray(model.predict(X), dtype=float) / k
        return out

    def save(self, path) -> None:
        import joblib

        joblib.dump(
            {"models": self.models, "cols": self._train_cols, "horizon": self.horizon}, path
        )

    def load(self, path) -> RecursiveRidgeModel:
        import joblib

        doc = joblib.load(path)
        self.models = doc["models"]
        self._train_cols = doc["cols"]
        self.horizon = doc["horizon"]
        return self
