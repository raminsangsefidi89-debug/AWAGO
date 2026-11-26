"""Experiment runner: walk-forward evaluation of every model family.

One harness for everything (P3): models are plugins behind ``ForecastModel``
and are compared on identical walk-forward rows against the naive baseline,
with Diebold-Mariano tests + Holm correction, probabilistic coverage
reporting, and persisted leaderboards carrying an honest verdict string.

Compute budget: lite profile runs a small pair/horizon/fold matrix
(a few minutes on CPU); ``full`` expands it. The runner never tunes on the
test rows: any weighting/meta-learning uses strictly earlier out-of-fold
predictions.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.config import DATA_DIR, Settings, get_settings
from app.db.models import MetricRecord
from app.logging_config import get_logger
from app.repro import config_hash, make_run_id, snapshot_hash
from app.services.evaluation.metrics import (
    diebold_mariano,
    full_metric_suite,
    holm_bonferroni,
    verdict_vs_baseline,
)
from app.services.evaluation.walkforward import purged_splits
from app.services.features.builders import build_feature_frame
from app.services.models.base import FitData, PredictData
from app.services.models.ensembles import (
    average_ensemble,
    inverse_error_ensemble,
    online_decayed_ensemble,
    stacking_ensemble,
)
from app.services.models.lifecycle import compare_and_maybe_promote
from app.services.models.probabilistic import (
    adaptive_conformal,
    coverage_report,
    cqr_conformal,
    split_conformal,
)
from app.services.models.registry import core_model_names, get_model

logger = get_logger(__name__)

QUANTILE_GRID: tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)


def _bars_frame(session: Session, pair: str) -> pd.DataFrame:
    from app.services.market import get_history

    bars = get_history(session, pair)
    return pd.DataFrame(
        {
            "timestamp": [b.timestamp for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
        }
    )


def _make_fit_data(
    pair: str,
    horizon: int,
    features: pd.DataFrame,
    close: pd.Series,
    target: pd.Series,
    idx: np.ndarray,
) -> FitData:
    ts = pd.DatetimeIndex(features["timestamp"].iloc[idx])
    return FitData(
        pair_symbol=pair,
        horizon=horizon,
        history=pd.Series(close.to_numpy()[idx], index=ts),
        features=features.iloc[idx].reset_index(drop=True),
        target=target.iloc[idx].reset_index(drop=True),
        timestamps=ts,
    )


def _make_predict_data(
    pair: str, horizon: int, features: pd.DataFrame, close: pd.Series, idx: np.ndarray
) -> PredictData:
    ts = pd.DatetimeIndex(features["timestamp"].iloc[idx])
    return PredictData(
        pair_symbol=pair,
        horizon=horizon,
        history=pd.Series(close.to_numpy()[idx], index=ts),
        features=features.iloc[idx].reset_index(drop=True),
        timestamps=ts,
    )


def _wf_predict(
    model_name: str,
    horizon: int,
    features: pd.DataFrame,
    close: pd.Series,
    target: pd.Series,
    splits: list[tuple[np.ndarray, np.ndarray]],
    pair: str,
) -> tuple[np.ndarray, np.ndarray, dict[float, np.ndarray], Any]:
    """Walk-forward prediction for one model. Returns
    (test_indices, preds, quantile_preds_dict, last_fitted_model)."""
    all_idx: list[np.ndarray] = []
    all_preds: list[np.ndarray] = []
    all_q: dict[float, list[np.ndarray]] = {q: [] for q in QUANTILE_GRID}
    model = get_model(model_name, horizon=horizon)
    for train_idx, test_idx in splits:
        fit_data = _make_fit_data(pair, horizon, features, close, target, train_idx)
        model.fit(fit_data)
        pred_data = _make_predict_data(pair, horizon, features, close, test_idx)
        preds = model.predict(pred_data)
        q_preds = model.predict_quantiles(pred_data, QUANTILE_GRID)
        all_idx.append(test_idx)
        all_preds.append(preds)
        if q_preds:
            for q in QUANTILE_GRID:
                if q in q_preds:
                    all_q[q].append(q_preds[q])
    test_idx_all = np.concatenate(all_idx)
    preds_all = np.concatenate(all_preds)
    q_out: dict[float, Any] = {
        q: np.concatenate(parts) if len(parts) == len(splits) else None
        for q, parts in all_q.items()
    }
    return test_idx_all, preds_all, {q: v for q, v in q_out.items() if v is not None}, model


def run_experiment(
    session: Session,
    pairs: list[str] | None = None,
    horizons: list[int] | None = None,
    model_names: list[str] | None = None,
    settings: Settings | None = None,
    quick: bool = False,
    scheme: str = "expanding",
    n_splits: int | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    registry_base: Path | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    pairs = pairs or settings.pairs_list[:2] if quick else pairs or settings.pairs_list
    horizons = horizons or [1, 7] if quick else horizons or settings.horizons_list
    model_names = model_names or core_model_names()
    n_splits = n_splits or (3 if quick else settings.walkforward_splits)
    started = time.monotonic()

    frames = {p: _bars_frame(session, p) for p in pairs}
    snap = snapshot_hash(
        [
            (p, len(df), float(df["close"].iloc[-1]) if len(df) else 0.0)
            for p, df in sorted(frames.items())
        ]
    )
    run_id = make_run_id("experiment", settings=settings, snapshot=snap)
    cfg_hash = config_hash(settings)

    total_steps = max(1, len(pairs) * len(horizons))
    step = 0
    leaderboard: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": [],
        "coverage": [],
    }

    for pair in pairs:
        df = frames[pair]
        if len(df) < 120:
            logger.warning("Skipping %s: only %d bars", pair, len(df))
            continue
        features = build_feature_frame(df, frames, pair_symbol=pair)
        close = pd.Series(pd.to_numeric(df["close"]).to_numpy(dtype=float))
        # alignment: features and close share the bar rows
        n = len(features)
        close = close.iloc[:n].reset_index(drop=True)

        for horizon in horizons:
            step += 1
            if progress_cb:
                progress_cb(step / total_steps, f"{pair} h={horizon}")
            target = pd.Series(np.log(close.shift(-horizon) / close))
            valid = target.notna().to_numpy()
            valid_idx = np.where(valid)[0]
            if len(valid_idx) < 120:
                continue
            feats_v = features.iloc[valid_idx].reset_index(drop=True)
            close_v = close.iloc[valid_idx].reset_index(drop=True)
            target_v = target.iloc[valid_idx].reset_index(drop=True)
            try:
                splits = purged_splits(len(valid_idx), n_splits, horizon=horizon, scheme=scheme)
            except ValueError as exc:
                logger.warning("No splits for %s h=%s: %s", pair, horizon, exc)
                continue

            results: dict[str, dict[str, Any]] = {}
            quantile_store: dict[str, dict[float, np.ndarray]] = {}
            for m_name in model_names:
                try:
                    test_idx, preds, q_preds, fitted = _wf_predict(
                        m_name, horizon, feats_v, close_v, target_v, splits, pair
                    )
                except Exception as exc:
                    logger.warning("Model %s failed on %s h=%s: %s", m_name, pair, horizon, exc)
                    continue
                y_true = target_v.to_numpy()[test_idx]
                insample = close_v.to_numpy()[: splits[0][0][-1] + 1]
                metrics = full_metric_suite(
                    y_true, preds, insample, None, level=settings.prediction_interval_level
                )
                results[m_name] = {
                    "preds": preds,
                    "y_true": y_true,
                    "test_idx": test_idx,
                    "metrics": metrics,
                    "fitted": fitted,
                }
                if q_preds:
                    quantile_store[m_name] = q_preds

            if "baseline_naive" not in results:
                continue

            # --- ensembles over base models, fold-time-aware ---
            # For fold k the combiner's weights/meta are fit ONLY on OOF rows of
            # folds < k (fold 0 falls back to a plain average). No weight ever
            # sees the outcome of the row it is applied to.
            base_names = [
                m for m in results if m.startswith(("baseline_", "stat_", "ml_", "deep_"))
            ]
            if len(base_names) >= 2:
                y_true = results[base_names[0]]["y_true"]
                insample = close_v.to_numpy()[: splits[0][0][-1] + 1]
                base_preds = results["baseline_naive"]["preds"]
                fold_sizes = [len(te) for _, te in splits]
                ensemble_specs = {
                    "ensemble_avg": "avg",
                    "ensemble_inv_error": "inv_error",
                    "ensemble_online": "online",
                    "ensemble_stacking": "stacking",
                }
                for e_name, e_kind in ensemble_specs.items():
                    combo_preds = np.zeros_like(base_preds)
                    offset = 0
                    ok = True
                    for k, m in enumerate(fold_sizes):
                        chunk = slice(offset, offset + m)
                        test_preds_k = {n_: results[n_]["preds"][chunk] for n_ in base_names}
                        base_test = base_preds[chunk]
                        if k == 0 or e_kind == "avg":
                            combo_preds[chunk] = average_ensemble(test_preds_k, base_test)
                        else:
                            oof_preds = {n_: results[n_]["preds"][:offset] for n_ in base_names}
                            y_oof = y_true[:offset]
                            try:
                                if e_kind == "inv_error":
                                    combo_preds[chunk] = inverse_error_ensemble(
                                        oof_preds, y_oof, test_preds_k, base_test
                                    )
                                elif e_kind == "online":
                                    combo_preds[chunk] = online_decayed_ensemble(
                                        oof_preds, y_oof, test_preds_k, base_test
                                    )
                                elif e_kind == "stacking":
                                    combo_preds[chunk] = stacking_ensemble(
                                        oof_preds, y_oof, test_preds_k, base_test
                                    )
                            except Exception as exc:
                                logger.warning("Ensemble %s fold %d failed: %s", e_name, k, exc)
                                combo_preds[chunk] = average_ensemble(test_preds_k, base_test)
                                ok = False
                        offset += m
                    results[e_name] = {
                        "preds": combo_preds,
                        "y_true": y_true,
                        "test_idx": results[base_names[0]]["test_idx"],
                        "metrics": full_metric_suite(
                            y_true, combo_preds, insample, None, settings.prediction_interval_level
                        ),
                        "fitted": None,
                    }
                    if not ok:
                        results[e_name]["metrics"]["note"] = "some folds fell back to baseline"

            # --- comparisons vs naive baseline (DM + Holm) ---
            base_result = results["baseline_naive"]
            pvals: list[tuple[str, float]] = []
            dm_results: dict[str, dict[str, float]] = {}
            for m_name, res in results.items():
                if m_name == "baseline_naive":
                    continue
                dm = diebold_mariano(
                    res["y_true"] - res["preds"],
                    base_result["y_true"] - base_result["preds"],
                    h=horizon,
                )
                dm_results[m_name] = dm
                pvals.append((m_name, dm["p_value"]))
            adjusted = holm_bonferroni(pvals) if pvals else {}

            for m_name, res in results.items():
                m = res["metrics"]
                dm_res: dict[str, float] | None = dm_results.get(m_name)
                verdict = (
                    "baseline (yardstick)"
                    if m_name == "baseline_naive"
                    else verdict_vs_baseline(m["mae"], base_result["metrics"]["mae"], dm_res)
                )
                row = {
                    "pair_symbol": pair,
                    "target_horizon": horizon,
                    "model_name": m_name[:64],
                    "mae": round(m["mae"], 8),
                    "rmse": round(m["rmse"], 8),
                    "mase": round(m.get("mase", float("nan")), 6),
                    "smape": round(m.get("smape", float("nan")), 6),
                    "directional_accuracy": round(m.get("directional_accuracy", float("nan")), 4),
                    "beats_baseline": bool(m["mae"] < base_result["metrics"]["mae"]),
                    "baseline_mae": round(base_result["metrics"]["mae"], 8),
                    "verdict": verdict,
                    "dm_p_value": round(dm_res["p_value"], 6) if dm_res else None,
                    "dm_p_holm": round(adjusted.get(m_name, 1.0), 6) if dm_res else None,
                }
                leaderboard["rows"].append(row)
                # persist to metric_records (v1 schema; extras in details_json)
                details = {
                    "run_id": run_id,
                    "feature_set_version": settings.feature_set_version,
                    "mase": row["mase"],
                    "verdict": row["verdict"],
                    "dm_p_value": row["dm_p_value"],
                    "dm_p_holm": row["dm_p_holm"],
                }
                session.add(
                    MetricRecord(
                        model_name=m_name[:64],
                        pair_symbol=pair,
                        horizon=horizon,
                        mae=row["mae"],
                        rmse=row["rmse"],
                        smape=row["smape"] if np.isfinite(row["smape"]) else 0.0,
                        directional_accuracy=row["directional_accuracy"]
                        if np.isfinite(row["directional_accuracy"])
                        else 0.0,
                        baseline_mae=row["baseline_mae"],
                        baseline_rmse=round(base_result["metrics"]["rmse"], 8),
                        beats_baseline=row["beats_baseline"],
                        n_test=len(res["y_true"]),
                        data_source="demo",
                        details_json=json.dumps(details),
                    )
                )
                # champion/challenger audit trail for the best few
                if (
                    m_name not in ("baseline_naive",)
                    and res["fitted"] is not None
                    and row["beats_baseline"]
                ):
                    compare_and_maybe_promote(
                        m_name,
                        res["y_true"] - res["preds"],
                        base_result["y_true"] - base_result["preds"],
                        pair,
                        horizon,
                        registry_base,
                    )
            session.commit()

            # --- probabilistic coverage ---
            y_true_all = base_result["y_true"]
            prob_rows = []
            for level in (0.80, 0.90):
                alpha_lo, alpha_hi = (1.0 - level) / 2.0, 1.0 - (1.0 - level) / 2.0
                # split conformal on the best point model's residuals
                for point_model in ("ml_ridge", "baseline_ets"):
                    if point_model not in results:
                        continue
                    res = results[point_model]
                    y, p = res["y_true"], res["preds"]
                    sc = split_conformal(y, p, nominal_level=level)
                    prob_rows.append(
                        coverage_report(
                            y, sc["lower"], sc["upper"], f"split_conformal[{point_model}]", level
                        ).as_dict()
                    )
                    ac = adaptive_conformal(y, p, nominal_level=level)
                    prob_rows.append(
                        coverage_report(
                            y, ac["lower"], ac["upper"], f"adaptive_conformal[{point_model}]", level
                        ).as_dict()
                    )
                # CQR via quantile GBM
                if "prob_quantile_gbm" in quantile_store:
                    qm = quantile_store["prob_quantile_gbm"]
                    if alpha_lo in qm and alpha_hi in qm:
                        cqr = cqr_conformal(
                            y_true_all, qm[alpha_lo], qm[alpha_hi], nominal_level=level
                        )
                        prob_rows.append(
                            coverage_report(
                                y_true_all, cqr["lower"], cqr["upper"], "cqr[quantile_gbm]", level
                            ).as_dict()
                        )
                    if qm:
                        from app.services.evaluation.metrics import crps_from_quantiles

                        prob_rows.append(
                            {
                                "method": "quantile_gbm_crps",
                                "nominal_level": level,
                                "empirical_coverage": coverage_report(
                                    y_true_all,
                                    qm.get(alpha_lo, y_true_all),
                                    qm.get(alpha_hi, y_true_all),
                                    "quantile_gbm",
                                    level,
                                ).empirical_coverage,
                                "mean_width": float(
                                    np.nanmean(
                                        qm.get(alpha_hi, y_true_all) - qm.get(alpha_lo, y_true_all)
                                    )
                                )
                                if alpha_lo in qm and alpha_hi in qm
                                else float("nan"),
                                "n": len(y_true_all),
                                "crps": round(crps_from_quantiles(y_true_all, qm), 8),
                            }
                        )
            leaderboard["coverage"].extend(
                [{"pair_symbol": pair, "target_horizon": horizon, **r} for r in prob_rows]
            )

            # persist walk-forward predictions (best model) for backtests/inspection
            try:
                pred_dir = (registry_base or DATA_DIR) / "leaderboards" / f"{run_id}_preds"
                pred_dir.mkdir(parents=True, exist_ok=True)
                best_name = min(
                    (n_ for n_ in results if n_ != "baseline_naive"),
                    key=lambda n_: results[n_]["metrics"]["mae"],
                    default="baseline_naive",
                )
                best = results[best_name]
                np.savez_compressed(
                    pred_dir / f"{pair.replace('/', '_')}_h{horizon}.npz",
                    y_true=best["y_true"],
                    y_pred=best["preds"],
                    model=np.array(best_name),
                )
            except OSError as exc:
                logger.warning("Prediction persist failed: %s", exc)

    elapsed = time.monotonic() - started
    leaderboard["elapsed_seconds"] = round(elapsed, 2)
    leaderboard["n_rows"] = len(leaderboard["rows"])
    leaderboard["config_hash"] = cfg_hash
    leaderboard["snapshot_hash"] = snap
    leaderboard["models"] = model_names
    leaderboard["horizons"] = horizons
    leaderboard["pairs"] = pairs
    leaderboard["scheme"] = scheme
    leaderboard["n_splits"] = n_splits

    # persist leaderboard
    try:
        out_dir = (registry_base or DATA_DIR) / "leaderboards"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{run_id}.json").write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")
        (out_dir / "latest.json").write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Leaderboard persist failed: %s", exc)

    return leaderboard
