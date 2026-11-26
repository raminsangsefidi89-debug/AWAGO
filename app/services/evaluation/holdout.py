"""Holdout protocol: the last slice of data is evaluated ONCE per model family.

Rules (recorded in ADR-0005):
* The holdout tail (default 20% of rows, min 60) is never used for fitting,
  selection, weighting, or conformal calibration anywhere else.
* Each model *family* (baseline / statistical / ml / deep / ensemble) gets one
  evaluation on the holdout — the family representative is chosen by
  walk-forward validation MAE on the pre-holdout rows only.
* The result is labeled "held out, evaluated once" and is the only number
  reported as the generalization estimate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from app.logging_config import get_logger

logger = get_logger(__name__)

FAMILY_PREFIXES = {
    "baseline": ("baseline_",),
    "statistical": ("stat_",),
    "ml": ("ml_",),
    "deep": ("deep_",),
    "ensemble": ("ensemble_",),
    "probabilistic": ("prob_",),
}


def family_of(model_name: str) -> str:
    for family, prefixes in FAMILY_PREFIXES.items():
        if model_name.startswith(prefixes):
            return family
    return "other"


def split_holdout(
    n: int, holdout_fraction: float = 0.2, min_holdout: int = 60
) -> tuple[np.ndarray, np.ndarray]:
    """Chronological development/holdout split. Holdout is the tail."""
    n_holdout = max(min_holdout, int(n * holdout_fraction))
    n_holdout = min(n_holdout, n // 2)
    dev_idx = np.arange(0, n - n_holdout)
    hold_idx = np.arange(n - n_holdout, n)
    return dev_idx, hold_idx


def evaluate_holdout(
    dev_results: dict[str, dict[str, Any]],
    run_family_rep: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Pick one representative per family (by dev MAE) and evaluate once.

    ``dev_results``: model_name -> {"mae": float} from walk-forward validation.
    ``run_family_rep(model_name)`` must fit on the development rows ONLY and
    return {"y_true", "preds", "metrics"} computed on the holdout rows.
    """
    best_per_family: dict[str, tuple[str, float]] = {}
    for name, res in dev_results.items():
        family = family_of(name)
        mae = float(res.get("mae", float("inf")))
        if family not in best_per_family or mae < best_per_family[family][1]:
            best_per_family[family] = (name, mae)

    out: dict[str, Any] = {"protocol": "holdout-evaluated-once", "families": {}}
    for family, (name, dev_mae) in sorted(best_per_family.items()):
        try:
            result = run_family_rep(name)
        except Exception as exc:
            out["families"][family] = {"representative": name, "error": str(exc)[:200]}
            continue
        out["families"][family] = {
            "representative": name,
            "dev_mae": round(dev_mae, 8),
            "holdout_metrics": result.get("metrics"),
            "n_holdout": len(result.get("y_true", [])),
            "label": "held out, evaluated once",
        }
    return out
