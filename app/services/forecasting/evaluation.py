"""Evaluation metrics and chronological walk-forward validation.

Rules enforced here:
  * Splits are strictly chronological (sklearn TimeSeriesSplit) — never random.
  * Every model is compared to the naive baseline; results state honestly
    whether the model beats it.
  * Residuals from walk-forward holdouts drive the prediction intervals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.model_selection import TimeSeriesSplit

# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Symmetric MAPE in percent (0..200 scale, typical FX usage -> small)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    valid = denom > 1e-12
    if not np.any(valid):
        return float("nan")
    return float(np.mean(np.abs(y_true[valid] - y_pred[valid]) / denom[valid]) * 100.0)


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    valid = np.abs(y_true) > 1e-12
    if not np.any(valid):
        return float("nan")
    return float(np.mean(np.abs(y_true[valid] - y_pred[valid]) / np.abs(y_true[valid])) * 100.0)


def directional_accuracy(
    y_true_price: np.ndarray,
    y_pred_price: np.ndarray,
    last_close: np.ndarray,
    eps: float = 1e-12,
) -> float | None:
    """Share of samples where the predicted move direction matches the actual one.

    Returns None when no sample has a non-zero predicted move (e.g. the naive
    baseline predicts no change and therefore has no direction).
    """
    true_move = np.asarray(y_true_price, dtype=float) - np.asarray(last_close, dtype=float)
    pred_move = np.asarray(y_pred_price, dtype=float) - np.asarray(last_close, dtype=float)
    has_direction = np.abs(pred_move) > eps
    if not np.any(has_direction):
        return None
    correct = np.sign(pred_move[has_direction]) == np.sign(true_move[has_direction])
    return float(np.mean(correct) * 100.0)


# ----------------------------------------------------------------------
# Walk-forward evaluation
# ----------------------------------------------------------------------


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward predictions and metrics for one model/horizon."""

    model_name: str
    horizon: int
    y_true_price: np.ndarray
    y_pred_price: np.ndarray
    last_close: np.ndarray
    y_true_logret: np.ndarray
    y_pred_logret: np.ndarray
    test_indices: np.ndarray
    fold_sizes: list[int] = field(default_factory=list)

    @property
    def residuals_logret(self) -> np.ndarray:
        return self.y_true_logret - self.y_pred_logret

    def metrics(self) -> dict:
        return {
            "mae": mae(self.y_true_price, self.y_pred_price),
            "rmse": rmse(self.y_true_price, self.y_pred_price),
            "smape": smape(self.y_true_price, self.y_pred_price),
            "mape": mape(self.y_true_price, self.y_pred_price),
            "directional_accuracy": directional_accuracy(
                self.y_true_price, self.y_pred_price, self.last_close
            ),
            "n_test": len(self.y_true_price),
        }


def walk_forward_indices(n_samples: int, n_splits: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
    """Chronological (train, test) index pairs — expanding window."""
    # TimeSeriesSplit requires n_splits >= 2 and at least 3 samples.
    n_splits = max(2, min(n_splits, max(2, n_samples // 20)))
    tscv = TimeSeriesSplit(n_splits=n_splits)
    X_dummy = np.zeros((n_samples, 1))
    return [(tr, te) for tr, te in tscv.split(X_dummy)]


def walk_forward_evaluate(
    X: np.ndarray,
    y_logret: np.ndarray,
    close_at_t: np.ndarray,
    close_at_t_plus_h: np.ndarray,
    horizon: int,
    model_factory,
    n_splits: int = 5,
    model_name: str = "model",
) -> WalkForwardResult:
    """Evaluate a model with expanding-window walk-forward validation.

    ``model_factory`` returns an unfitted estimator (e.g. a Pipeline with its
    own scaler, fit on training folds only — no leakage).
    """
    n = len(X)
    preds_logret: list[float] = []
    trues_logret: list[float] = []
    lasts: list[float] = []
    trues_price: list[float] = []
    indices: list[int] = []
    fold_sizes: list[int] = []

    for train_idx, test_idx in walk_forward_indices(n, n_splits):
        model = model_factory()
        model.fit(X[train_idx], y_logret[train_idx])
        pred = model.predict(X[test_idx])
        preds_logret.extend(pred.tolist())
        trues_logret.extend(y_logret[test_idx].tolist())
        lasts.extend(close_at_t[test_idx].tolist())
        trues_price.extend(close_at_t_plus_h[test_idx].tolist())
        indices.extend(test_idx.tolist())
        fold_sizes.append(len(test_idx))

    preds_logret_arr = np.asarray(preds_logret, dtype=float)
    last_arr = np.asarray(lasts, dtype=float)
    pred_price = last_arr * np.exp(preds_logret_arr)

    return WalkForwardResult(
        model_name=model_name,
        horizon=horizon,
        y_true_price=np.asarray(trues_price, dtype=float),
        y_pred_price=pred_price,
        last_close=last_arr,
        y_true_logret=np.asarray(trues_logret, dtype=float),
        y_pred_logret=preds_logret_arr,
        test_indices=np.asarray(indices, dtype=int),
        fold_sizes=fold_sizes,
    )


def residual_quantiles(residuals_logret: np.ndarray, level: float = 0.90) -> tuple[float, float]:
    """Empirical quantiles of walk-forward residuals in return space.

    Returns (q_lo, q_hi) such that roughly ``level`` of residuals fall inside.
    """
    alpha = (1.0 - level) / 2.0
    q_lo = float(np.quantile(residuals_logret, alpha))
    q_hi = float(np.quantile(residuals_logret, 1.0 - alpha))
    return q_lo, q_hi
