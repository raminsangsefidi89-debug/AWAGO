"""Ensemble combiners over walk-forward base-model predictions.

Explicit fit/predict API: weights and meta-models are fit on *past*
out-of-fold predictions (``fit_preds`` / ``fit_y``) and then applied to a
later block (``predict_preds``). Nothing ever sees the outcome of the rows
it is predicting. When a base model produces NaN or a combiner cannot be
fit, the fallback (baseline) column wins — "fall back to baseline" is a
first-class behaviour, not an afterthought.
"""

from __future__ import annotations

import numpy as np


def _clean(preds: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    out = np.asarray(preds, dtype=float).copy()
    if not np.isfinite(out).all():
        fb = np.asarray(fallback, dtype=float)
        fill = fb if fb.shape == out.shape else np.zeros_like(out)
        out = np.where(np.isfinite(out), out, fill)
    return out


def average_ensemble(predict_preds: dict[str, np.ndarray], fallback: np.ndarray) -> np.ndarray:
    stack = np.column_stack([_clean(p, fallback) for p in predict_preds.values()])
    return stack.mean(axis=1)


def inverse_error_ensemble(
    fit_preds: dict[str, np.ndarray],
    fit_y: np.ndarray,
    predict_preds: dict[str, np.ndarray],
    fallback: np.ndarray,
) -> np.ndarray:
    """Weight models by 1/MAE computed on ``fit_preds`` vs ``fit_y`` only."""
    weights: dict[str, float] = {}
    for name, p in fit_preds.items():
        err = float(np.nanmean(np.abs(np.asarray(fit_y) - np.asarray(p)))) if len(fit_y) else 1.0
        weights[name] = 1.0 / max(err, 1e-8)
    total = sum(weights.values()) or 1.0
    out = np.zeros(len(next(iter(predict_preds.values()))), dtype=float)
    for name, p in predict_preds.items():
        w = (
            weights.get(name, 1.0 / len(predict_preds)) / total
            if name in weights
            else 1.0 / len(predict_preds)
        )
        out += _clean(p, fallback) * w
    return out


def stacking_ensemble(
    fit_preds: dict[str, np.ndarray],
    fit_y: np.ndarray,
    predict_preds: dict[str, np.ndarray],
    fallback: np.ndarray,
) -> np.ndarray:
    """Ridge meta-model trained on out-of-fold base predictions."""
    from sklearn.linear_model import Ridge

    X_fit = np.column_stack([_clean(fit_preds[n], np.zeros(len(fit_y))) for n in predict_preds])
    X_pred = np.column_stack([_clean(predict_preds[n], fallback) for n in predict_preds])
    meta = Ridge(alpha=1.0)
    meta.fit(X_fit, np.asarray(fit_y, dtype=float))
    return np.asarray(meta.predict(X_pred), dtype=float)


def online_decayed_ensemble(
    fit_preds: dict[str, np.ndarray],
    fit_y: np.ndarray,
    predict_preds: dict[str, np.ndarray],
    fallback: np.ndarray,
    decay: float = 0.97,
) -> np.ndarray:
    """Exponentially-decayed weighting over realized errors on the fit block."""
    names = list(predict_preds)
    weights = np.ones(len(names))
    fit_arr = np.column_stack([_clean(fit_preds[n], np.zeros(len(fit_y))) for n in names])
    y = np.asarray(fit_y, dtype=float)
    for t in range(len(y)):
        errors = np.abs(y[t] - fit_arr[t])
        weights = decay * weights + (1.0 - decay) * (1.0 / (errors + 1e-8))
    total = weights.sum() or 1.0
    pred_arr = np.column_stack([_clean(predict_preds[n], fallback) for n in names])
    return (pred_arr * (weights / total)).sum(axis=1)


def ensemble_names() -> list:
    return ["ensemble_avg", "ensemble_inv_error", "ensemble_stacking", "ensemble_online"]
