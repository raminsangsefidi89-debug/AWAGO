"""Model training: candidates, walk-forward comparison, honest baselines.

Training is NEVER triggered automatically by server startup. It runs from:
  * the launcher's optional first-run seeding (AUTO_TRAIN_ON_SEED=true),
  * the CLI (scripts/train_models.py),
  * an authenticated API job (POST /api/v1/jobs/train).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.config import Settings, get_settings
from app.db.models import MetricRecord, ModelArtifact
from app.logging_config import get_logger
from app.services.features import FEATURES_VERSION, build_feature_frame, feature_columns
from app.services.forecasting.evaluation import (
    directional_accuracy,
    mae,
    mape,
    residual_quantiles,
    rmse,
    smape,
    walk_forward_evaluate,
    walk_forward_indices,
)
from app.services.forecasting.persistence import model_path, save_bundle
from app.services.market import get_history

logger = get_logger(__name__)

ProgressCallback = Callable[[float, str], None]

MIN_ROWS = 200
MIN_ROWS_QUICK = 150


# ----------------------------------------------------------------------
# Candidate models (scalers are inside pipelines -> fit on train folds only)
# ----------------------------------------------------------------------


def _make_ridge() -> Pipeline:
    return Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0, random_state=None))])


def _make_hist_gb():
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(
        max_iter=200,
        learning_rate=0.05,
        max_depth=4,
        l2_regularization=0.1,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=15,
        random_state=42,
    )


def _make_hist_gb_quick():
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(
        max_iter=80,
        learning_rate=0.06,
        max_depth=3,
        early_stopping=False,
        random_state=42,
    )


def _make_lightgbm():
    from lightgbm import LGBMRegressor

    return LGBMRegressor(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        verbose=-1,
    )


def _make_lightgbm_quick():
    from lightgbm import LGBMRegressor

    return LGBMRegressor(
        n_estimators=120,
        learning_rate=0.06,
        num_leaves=21,
        random_state=42,
        verbose=-1,
    )


def lightgbm_available() -> bool:
    try:
        import lightgbm  # noqa: F401

        return True
    except Exception:
        return False


def candidate_factories(quick: bool = False) -> dict[str, Callable[[], Any]]:
    factories: dict[str, Callable[[], object]] = {
        "ridge": _make_ridge,
        "hist_gb": _make_hist_gb_quick if quick else _make_hist_gb,
    }
    if lightgbm_available():
        factories["lightgbm"] = _make_lightgbm_quick if quick else _make_lightgbm
    else:
        logger.info("LightGBM not installed; skipping lightgbm candidate (this is fine)")
    return factories


# ----------------------------------------------------------------------
# Training
# ----------------------------------------------------------------------


def _compute_baseline_logret_preds(
    frame: pd.DataFrame, mask: np.ndarray, horizon: int
) -> dict[str, np.ndarray]:
    """Baseline predictions in return space for the masked rows.

    naive: 0.0 (price unchanged). drift: mean log-return of the trailing
    20 days (min 5) times the horizon.
    """
    ret = np.log(frame["close"] / frame["close"].shift(1))
    wmean = ret.rolling(20, min_periods=5).mean()
    naive = np.zeros(int(mask.sum()), dtype=float)
    drift = (wmean[mask] * horizon).fillna(0.0).to_numpy(dtype=float)
    return {"naive": naive, "drift": drift}


def train_pair(
    session,
    pair_symbol: str,
    horizons: list[int] | None = None,
    settings: Settings | None = None,
    quick: bool = False,
    progress: ProgressCallback | None = None,
) -> dict:
    """Train and persist models for one pair across the given horizons.

    Returns a summary dict. Every candidate is compared to the naive
    baseline on identical walk-forward test rows; the winner is persisted,
    and the comparison states honestly whether it beats the baseline.
    """
    settings = settings or get_settings()
    horizons = horizons or settings.horizons_list
    min_rows = MIN_ROWS_QUICK if quick else MIN_ROWS

    def report(frac: float, msg: str) -> None:
        if progress:
            progress(max(0.0, min(1.0, frac)), msg)

    report(0.02, f"Loading history for {pair_symbol}")
    bars = get_history(session, pair_symbol)
    if len(bars) < min_rows:
        raise ValueError(
            f"{pair_symbol}: need at least {min_rows} bars to train, have {len(bars)}. "
            "Run data collection / seeding first."
        )

    df = pd.DataFrame(
        {
            "timestamp": [b.timestamp for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
        }
    )
    data_source = bars[-1].data_source

    report(0.08, "Building features")
    frame = build_feature_frame(df, horizons)
    feats = feature_columns()
    n_splits = 3 if quick else 5
    interval_level = settings.prediction_interval_level

    results: dict[str, Any] = {
        "pair_symbol": pair_symbol,
        "data_source": data_source,
        "horizons": {},
    }

    for hi, h in enumerate(horizons):
        base_frac = 0.10 + 0.85 * (hi / max(1, len(horizons)))
        report(base_frac, f"Training horizon h={h}")

        mask = (
            frame[feats].notna().all(axis=1)
            & frame[f"target_logret_h{h}"].notna()
            & frame[f"target_close_h{h}"].notna()
        ).to_numpy()
        m = int(mask.sum())
        if m < min_rows:
            raise ValueError(f"{pair_symbol} h={h}: only {m} usable rows after feature warm-up")

        X = frame.loc[mask, feats].to_numpy(dtype=float)
        y_logret = frame.loc[mask, f"target_logret_h{h}"].to_numpy(dtype=float)
        close_t = frame.loc[mask, "close"].to_numpy(dtype=float)
        close_th = frame.loc[mask, f"target_close_h{h}"].to_numpy(dtype=float)

        folds = walk_forward_indices(m, n_splits)
        test_idx = np.concatenate([te for _, te in folds]) if folds else np.array([], dtype=int)

        # --- baselines on identical test rows ---
        baseline_preds = _compute_baseline_logret_preds(frame, mask, h)
        baseline_metrics: dict[str, dict] = {}
        for bname, bpred_logret in baseline_preds.items():
            b_pred_price = close_t * np.exp(bpred_logret)
            baseline_metrics[bname] = {
                "mae": mae(close_th[test_idx], b_pred_price[test_idx]),
                "rmse": rmse(close_th[test_idx], b_pred_price[test_idx]),
                "smape": smape(close_th[test_idx], b_pred_price[test_idx]),
                "mape": mape(close_th[test_idx], b_pred_price[test_idx]),
                "directional_accuracy": directional_accuracy(
                    close_th[test_idx], b_pred_price[test_idx], close_t[test_idx]
                ),
                "n_test": len(test_idx),
            }

        naive_mae = baseline_metrics["naive"]["mae"]
        naive_rmse = baseline_metrics["naive"]["rmse"]

        # --- candidates ---
        candidate_results: dict[str, dict] = {}
        wf_results = {}
        factories = candidate_factories(quick=quick)
        for ci, (name, factory) in enumerate(factories.items()):
            report(
                base_frac + 0.85 * (ci / max(1, len(factories))) / max(1, len(horizons)),
                f"Walk-forward evaluation: {name} (h={h})",
            )
            wf = walk_forward_evaluate(
                X, y_logret, close_t, close_th, h, factory, n_splits=n_splits, model_name=name
            )
            wf.folds = folds  # type: ignore[attr-defined]
            wf_results[name] = wf
            met = wf.metrics()
            met["beats_baseline"] = bool(met["mae"] < naive_mae)
            met["mae_ratio_vs_naive"] = round(met["mae"] / naive_mae, 4) if naive_mae > 0 else None
            met["rmse_ratio_vs_naive"] = (
                round(met["rmse"] / naive_rmse, 4) if naive_rmse > 0 else None
            )
            candidate_results[name] = met

        if not candidate_results:
            raise RuntimeError("No model candidates available")

        winner = min(candidate_results.items(), key=lambda kv: kv[1]["mae"])[0]

        # --- refit winner on all usable rows and persist ---
        report(base_frac + 0.9 / max(1, len(horizons)), f"Refitting winner '{winner}' (h={h})")
        final_model = factories[winner]()
        final_model.fit(X, y_logret)

        wf_winner = wf_results[winner]
        q_lo, q_hi = residual_quantiles(wf_winner.residuals_logret, level=interval_level)

        trained_at = datetime.now(timezone.utc)
        bundle = {
            "model": final_model,
            "feature_cols": feats,
            "horizon": h,
            "model_name": winner,
            "pair_symbol": pair_symbol,
            "features_version": FEATURES_VERSION,
            "trained_at": trained_at.isoformat(),
            "train_start": df["timestamp"].iloc[0].isoformat(),
            "train_end": df["timestamp"].iloc[-1].isoformat(),
            "n_rows": m,
            "data_source": data_source,
            "interval_level": interval_level,
            "resid_q_lo": q_lo,
            "resid_q_hi": q_hi,
            "metrics": candidate_results[winner],
            "all_candidates": candidate_results,
            "baselines": baseline_metrics,
        }
        path = model_path(settings.models_dir, pair_symbol, h, winner)
        saved = save_bundle(path, bundle)

        # --- DB records (replace previous artifacts for identity) ---
        from sqlalchemy import delete

        session.execute(
            delete(ModelArtifact).where(
                ModelArtifact.pair_symbol == pair_symbol,
                ModelArtifact.horizon == h,
                ModelArtifact.data_source == data_source,
            )
        )
        session.execute(
            delete(MetricRecord).where(
                MetricRecord.pair_symbol == pair_symbol,
                MetricRecord.horizon == h,
                MetricRecord.data_source == data_source,
            )
        )
        session.add(
            ModelArtifact(
                pair_symbol=pair_symbol,
                horizon=h,
                model_name=winner,
                file_path=saved,
                trained_at=trained_at,
                train_start=pd.to_datetime(df["timestamp"].iloc[0]).to_pydatetime(),
                train_end=pd.to_datetime(df["timestamp"].iloc[-1]).to_pydatetime(),
                n_rows=m,
                features_version=FEATURES_VERSION,
                data_source=data_source,
                is_active=True,
                metrics_json=json.dumps(candidate_results[winner]),
                params_json=json.dumps({"quick": quick, "n_splits": n_splits}),
            )
        )
        for name, met in list(candidate_results.items()) + list(baseline_metrics.items()):
            beats = met.get("beats_baseline")
            if beats is None:
                beats = bool(met["mae"] < naive_mae)
            session.add(
                MetricRecord(
                    pair_symbol=pair_symbol,
                    horizon=h,
                    model_name=name,
                    mae=met["mae"],
                    rmse=met["rmse"],
                    smape=met["smape"],
                    directional_accuracy=(
                        met["directional_accuracy"]
                        if met["directional_accuracy"] is not None
                        else -1.0  # sentinel: no direction (documented in API)
                    ),
                    baseline_mae=naive_mae,
                    baseline_rmse=naive_rmse,
                    beats_baseline=beats,
                    n_test=met["n_test"],
                    evaluated_at=trained_at,
                    data_source=data_source,
                    details_json=json.dumps(
                        {
                            k: v
                            for k, v in met.items()
                            if k not in ("mae", "rmse", "smape", "directional_accuracy", "n_test")
                        }
                    ),
                )
            )
        session.commit()

        results["horizons"][str(h)] = {
            "winner": winner,
            "metrics": candidate_results[winner],
            "baselines": baseline_metrics,
            "interval_quantiles": {"q_lo": q_lo, "q_hi": q_hi, "level": interval_level},
            "model_path": saved,
        }

    report(1.0, "Training complete")
    return results
