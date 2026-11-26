"""Feature selection: redundancy clustering + stability selection.

Honest methodology:

* **Correlation clustering** is unsupervised (feature-vs-feature only), so it
  cannot leak the target. Representatives of each cluster are chosen by the
  lowest mean absolute correlation with the other features (no target use).
* **Stability selection** fits a ridge model on *time-ordered* folds and
  computes permutation importance per fold (fold-local, no shuffling across
  time). Features are kept when they rank in the top-k of at least
  ``stability_threshold`` of the folds. The output reports every fold's
  importance so a feature that only helps one regime is visible as such.

This is P1-grade pragmatic selection — not a substitute for the leakage
audit, which must run first.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.logging_config import get_logger

logger = get_logger(__name__)


def correlation_clustering(features: pd.DataFrame, threshold: float = 0.9) -> dict[str, list[str]]:
    """Group feature columns into |corr| >= threshold clusters (greedy)."""
    cols = [c for c in features.columns if c not in ("timestamp", "pair_symbol")]
    corr = features[cols].corr().abs().fillna(0.0)
    clusters: list[list[str]] = []
    assigned: set[str] = set()
    for col in cols:
        if col in assigned:
            continue
        cluster = [col]
        assigned.add(col)
        for other in cols:
            if other in assigned:
                continue
            if all(corr.loc[other, c] >= threshold for c in cluster):
                cluster.append(other)
                assigned.add(other)
        clusters.append(cluster)

    # Representative = column with the lowest mean |corr| to other features.
    result: dict[str, list[str]] = {}
    for cluster in clusters:
        rep = min(cluster, key=lambda c: (corr.loc[c, [x for x in cols if x != c]].mean(), c))
        result[rep] = sorted(x for x in cluster if x != rep)
    return result


def _permutation_importance(
    model, X: pd.DataFrame, y: np.ndarray, seed: int = 0
) -> dict[str, float]:
    from sklearn.metrics import mean_absolute_error

    rng = np.random.default_rng(seed)
    baseline = mean_absolute_error(y, model.predict(X))
    importances: dict[str, float] = {}
    for col in X.columns:
        X_perm = X.copy()
        X_perm[col] = rng.permutation(X_perm[col].to_numpy())
        score = mean_absolute_error(y, model.predict(X_perm))
        importances[col] = float(score - baseline)
    return importances


def stability_selection(
    features: pd.DataFrame,
    target: pd.Series,
    n_splits: int = 4,
    top_k: int = 10,
    stability_threshold: float = 0.6,
    seed: int = 42,
) -> dict:
    """Rank features by fold-local permutation importance stability."""
    from sklearn.linear_model import Ridge

    cols = [c for c in features.columns if c not in ("timestamp", "pair_symbol")]
    frame = features[cols].copy()
    frame["__y__"] = target.to_numpy()
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 100 or n_splits < 2:
        return {
            "selected": cols,
            "note": "series too short for stability selection; all features kept",
        }

    X, y = frame[cols], frame["__y__"].to_numpy()
    fold_sizes = len(X) // (n_splits + 1)  # expanding window: train grows, test rolls
    fold_importances: list[dict[str, float]] = []
    top_counts: dict[str, int] = {c: 0 for c in cols}

    for k in range(n_splits):
        test_start = fold_sizes * (k + 1)
        test_end = min(test_start + fold_sizes, len(X))
        if test_end - test_start < 20:
            continue
        X_train, y_train = X.iloc[:test_start], y[:test_start]
        X_test, y_test = X.iloc[test_start:test_end], y[test_start:test_end]
        model = Ridge(alpha=1.0, random_state=None)
        model.fit(X_train, y_train)
        imp = _permutation_importance(model, X_test, y_test, seed=seed + k)
        fold_importances.append(imp)
        ranked = sorted(imp, key=lambda c: -imp[c])[:top_k]
        for col in ranked:
            top_counts[col] += 1

    if not fold_importances:
        return {"selected": cols, "note": "no usable folds; all features kept"}

    n_folds = len(fold_importances)
    selected = sorted(
        [c for c in cols if top_counts[c] / n_folds >= stability_threshold],
        key=lambda c: -np.mean([imp.get(c, 0.0) for imp in fold_importances]),
    )
    return {
        "selected": selected,
        "n_folds": n_folds,
        "stability_threshold": stability_threshold,
        "selection_frequency": {c: round(top_counts[c] / n_folds, 3) for c in cols},
        "mean_importance": {
            c: round(float(np.mean([imp.get(c, 0.0) for imp in fold_importances])), 5) for c in cols
        },
    }


def select_features(
    features: pd.DataFrame,
    target: pd.Series,
    corr_threshold: float = 0.9,
    **stability_kwargs,
) -> dict:
    """Full pipeline: de-duplicate by clustering, then stability-select."""
    clusters = correlation_clustering(features, threshold=corr_threshold)
    reps = sorted(clusters.keys())
    reduced = (
        features[["timestamp", "pair_symbol", *reps]]
        if "pair_symbol" in features.columns
        else features[reps]
    )
    stability = stability_selection(reduced, target, **stability_kwargs)
    selected = stability.get("selected", reps)
    return {
        "selected": selected,
        "correlation_clusters": clusters,
        "stability": stability,
        "dropped_redundant": sorted(x for members in clusters.values() for x in members),
    }
