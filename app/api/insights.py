"""Insight endpoints: features, regimes, volatility, probabilistic forecasts,
backtests (read stored predictions), explainability, and drift."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.errors import NotFoundError
from app.api.params import normalize_pair
from app.db.engine import get_db
from app.logging_config import get_logger

router = APIRouter(tags=["insights"])
logger = get_logger(__name__)

DISCLAIMER = "Educational and analytical use only. Not financial advice."


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


# ----------------------------------------------------------------------
# Feature sets
# ----------------------------------------------------------------------


@router.get("/features", summary="Feature-set registry (versioned)")
def get_features() -> dict:
    from app.services.features.set import get_feature_set

    fs = get_feature_set()
    doc = fs.as_dict()
    doc["point_in_time"] = (
        "Every feature row T uses only bars with timestamp <= T; "
        "the leakage-audit harness enforces this in tests."
    )
    return doc


# ----------------------------------------------------------------------
# Regimes
# ----------------------------------------------------------------------


@router.get("/regimes/{pair}", summary="Volatility regimes + change points")
def get_regimes(pair: str, db: Session = Depends(get_db)) -> dict:
    from app.services.features.regimes import cusum_change_points, regime_summary, vol_regime

    symbol = normalize_pair(pair)
    df = _bars_frame(db, symbol)
    if len(df) < 40:
        raise NotFoundError(f"Not enough data for regimes: {symbol}", code="insufficient_data")
    close = pd.Series(pd.to_numeric(df["close"]).to_numpy(dtype=float))
    rets = np.log(close / close.shift(1))
    labels = vol_regime(close, window=20)
    points = cusum_change_points(rets.dropna())
    ts = pd.to_datetime(df["timestamp"])
    return {
        "pair_symbol": symbol,
        "summary": regime_summary(close),
        "current_regime": str(labels.iloc[-1]),
        "change_points": [ts.iloc[i].isoformat() for i in points if i < len(ts)],
        "note": "Regimes are point-in-time overlays, not hindsight explanations.",
    }


# ----------------------------------------------------------------------
# Volatility
# ----------------------------------------------------------------------


@router.get("/volatility/{pair}", summary="Volatility forecast (method-labeled)")
def get_volatility(
    pair: str, horizon: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)
) -> dict:
    """Realized-vol summary + forward vol estimate.

    Method is always labeled: 'garch(1,1)' when the optional `arch` package
    is installed and fitted successfully, otherwise 'rolling-realized'
    (trailing std of log returns, scaled by sqrt(h) — a persistence-style
    forecast, not a model claim).
    """
    from app.services.models.statistical import HAS_ARCH

    symbol = normalize_pair(pair)
    df = _bars_frame(db, symbol)
    if len(df) < 40:
        raise NotFoundError(f"Not enough data for volatility: {symbol}", code="insufficient_data")
    close = pd.Series(pd.to_numeric(df["close"]).to_numpy(dtype=float))
    rets = np.log(close / close.shift(1)).dropna()
    rv20 = float(rets.rolling(20).std().iloc[-1])
    method = "rolling-realized"
    sigma_h = rv20 * np.sqrt(horizon)
    detail = "Trailing 20d realized vol scaled by sqrt(h) — persistence forecast."
    if HAS_ARCH and len(rets) >= 100:
        try:
            from app.services.models.base import FitData
            from app.services.models.statistical import GARCHModel

            ts = pd.DatetimeIndex(pd.to_datetime(df["timestamp"]))
            fit = FitData(
                symbol,
                horizon,
                close,
                pd.DataFrame({"timestamp": df["timestamp"]}),
                pd.Series(np.zeros(len(close))),
                ts,
            )
            garch = GARCHModel(horizon=horizon).fit(fit)
            sigma_h = garch.predict_sigma(horizon)
            method = "garch(1,1)"
            detail = "GARCH(1,1) h-step conditional volatility (optional arch package)."
        except Exception as exc:
            detail = f"GARCH fit failed ({exc}); fell back to rolling-realized."
    return {
        "pair_symbol": symbol,
        "horizon": horizon,
        "sigma_h": round(float(sigma_h), 8),
        "method": method,
        "detail": detail,
        "realized_vol_20d": round(rv20, 8),
        "is_demo_data": True,
        "disclaimer": DISCLAIMER,
    }


# ----------------------------------------------------------------------
# Probabilistic forecast
# ----------------------------------------------------------------------


@router.get("/forecasts/probabilistic/{pair}", summary="Quantile forecast + fan chart + method")
def probabilistic_forecast(
    pair: str,
    horizon: int = Query(7, ge=1, le=90),
    level: float = Query(0.90, ge=0.5, le=0.99),
    db: Session = Depends(get_db),
) -> dict:
    """Fan-chart data from walk-forward residual quantiles of a point model.

    Method (labeled in the response): 'wf-residual-quantiles' — quantiles of
    walk-forward prediction errors of Ridge, applied symmetrically around
    the point forecast. Empirical coverage of this method on the same data
    is reported alongside the nominal level — never just the nominal number.
    """
    from app.services.evaluation.walkforward import purged_splits
    from app.services.features.builders import build_feature_frame
    from app.services.models.base import FitData, PredictData
    from app.services.models.ml import RidgeModel

    symbol = normalize_pair(pair)
    df = _bars_frame(db, symbol)
    if len(df) < 150:
        raise NotFoundError(f"Not enough data for a forecast: {symbol}", code="insufficient_data")
    frames = {symbol: df}
    features = build_feature_frame(df, frames, pair_symbol=symbol)
    close = pd.Series(pd.to_numeric(df["close"]).to_numpy(dtype=float))
    target = pd.Series(np.log(close.shift(-horizon) / close))
    valid_idx = np.where(target.notna().to_numpy())[0]
    feats_v = features.iloc[valid_idx].reset_index(drop=True)
    close_v = close.iloc[valid_idx].reset_index(drop=True)
    target_v = target.iloc[valid_idx].reset_index(drop=True)

    try:
        splits = purged_splits(len(valid_idx), 3, horizon=horizon, scheme="expanding")
    except ValueError as exc:
        raise NotFoundError(str(exc), code="insufficient_data") from exc

    model = RidgeModel(horizon=horizon)
    preds, trues = [], []
    for train_idx, test_idx in splits:
        ts_train = pd.DatetimeIndex(feats_v["timestamp"].iloc[train_idx])
        model.fit(
            FitData(
                symbol,
                horizon,
                pd.Series(close_v.to_numpy()[train_idx], index=ts_train),
                feats_v.iloc[train_idx].reset_index(drop=True),
                target_v.iloc[train_idx].reset_index(drop=True),
                ts_train,
            )
        )
        ts_test = pd.DatetimeIndex(feats_v["timestamp"].iloc[test_idx])
        preds.append(
            model.predict(
                PredictData(
                    symbol,
                    horizon,
                    pd.Series(close_v.to_numpy()[test_idx], index=ts_test),
                    feats_v.iloc[test_idx].reset_index(drop=True),
                    ts_test,
                )
            )
        )
        trues.append(target_v.to_numpy()[test_idx])
    y_pred = np.concatenate(preds)
    y_true = np.concatenate(trues)
    residuals = y_true - y_pred

    alpha = (1.0 - level) / 2.0
    q_lo = float(np.quantile(residuals, alpha))
    q_hi = float(np.quantile(residuals, 1.0 - alpha))
    covered = float(np.mean((y_true >= y_pred + q_lo) & (y_true <= y_pred + q_hi)))
    last_close = float(close.iloc[-1])
    point = float(y_pred[-1])
    fan = []
    for frac in np.linspace(0.0, 1.0, max(2, horizon + 1)):
        fan.append(
            {
                "step": round(frac * horizon),
                "price": round(last_close * np.exp(point * frac), 6),
                "lower": round(last_close * np.exp((point + q_lo) * frac), 6),
                "upper": round(last_close * np.exp((point + q_hi) * frac), 6),
            }
        )
    return {
        "pair_symbol": symbol,
        "horizon": horizon,
        "method": "wf-residual-quantiles (Ridge point model, expanding WF)",
        "nominal_level": level,
        "empirical_coverage_on_wf": round(covered, 4),
        "point_forecast_log_return": round(point, 8),
        "residual_quantiles": {"lower": round(q_lo, 8), "upper": round(q_hi, 8)},
        "fan_chart": fan,
        "last_close": last_close,
        "caveat": "Empirical coverage is measured on the same walk-forward rows; nominal != guaranteed.",
        "disclaimer": DISCLAIMER,
    }


# ----------------------------------------------------------------------
# Backtests (from stored walk-forward predictions)
# ----------------------------------------------------------------------


@router.get("/backtests/{pair}", summary="Simulated backtest from stored WF predictions")
def get_backtest(
    pair: str,
    run_id: str = Query("", description="Experiment run id; empty = latest."),
    horizon: int = Query(7, ge=1, le=90),
    cost_bps: float = Query(1.0, ge=0, le=100),
    slippage_bps: float = Query(0.5, ge=0, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """SIMULATION ONLY. Uses walk-forward predictions stored by the runner."""
    from app.config import DATA_DIR
    from app.services.evaluation.backtest import simulate

    symbol = normalize_pair(pair)
    rid = run_id
    if not rid:
        latest = DATA_DIR / "leaderboards" / "latest.json"
        if not latest.exists():
            raise NotFoundError(
                "No experiment run yet — POST /api/v1/experiments/run first.", code="no_run"
            )
        rid = json.loads(latest.read_text(encoding="utf-8")).get("run_id", "")
    pred_path = (
        DATA_DIR / "leaderboards" / f"{rid}_preds" / f"{symbol.replace('/', '_')}_h{horizon}.npz"
    )
    if not pred_path.exists():
        raise NotFoundError(
            f"No stored predictions for {symbol} h={horizon} in run {rid}. "
            "Run an experiment covering this pair/horizon.",
            code="no_predictions",
        )
    data = np.load(pred_path)
    result = simulate(
        data["y_true"],
        data["y_pred"],
        cost_bps_per_side=cost_bps,
        slippage_bps_per_side=slippage_bps,
    )
    result["pair_symbol"] = symbol
    result["run_id"] = rid
    result["horizon"] = horizon
    return result


# ----------------------------------------------------------------------
# Explainability (permutation importance, time-ordered folds)
# ----------------------------------------------------------------------


@router.get("/explainability/{pair}", summary="Permutation importance (WF folds)")
def get_explainability(
    pair: str,
    horizon: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.features.builders import build_feature_frame
    from app.services.features.selection import select_features

    symbol = normalize_pair(pair)
    df = _bars_frame(db, symbol)
    if len(df) < 200:
        raise NotFoundError(f"Not enough data: {symbol}", code="insufficient_data")
    features = build_feature_frame(df, {symbol: df}, pair_symbol=symbol)
    close = pd.Series(pd.to_numeric(df["close"]).to_numpy(dtype=float))
    target = pd.Series(np.log(close.shift(-horizon) / close))
    result = select_features(features, target, n_splits=3, top_k=8)
    return {
        "pair_symbol": symbol,
        "horizon": horizon,
        "method": "fold-local permutation importance (expanding time-ordered folds, Ridge) + correlation clustering",
        "selected": result["selected"],
        "stability": result["stability"],
        "correlation_clusters": result["correlation_clusters"],
        "note": "Importances are in-forecast MAE increase units; PDP/SHAP skipped (documented).",
    }


# ----------------------------------------------------------------------
# Drift
# ----------------------------------------------------------------------


@router.get("/drift/{pair}", summary="Feature drift (KS) + staleness")
def get_drift(pair: str, db: Session = Depends(get_db)) -> dict:
    from scipy.stats import ks_2samp

    from app.services.features.builders import build_feature_frame
    from app.services.quality.engine import find_stale

    symbol = normalize_pair(pair)
    df = _bars_frame(db, symbol)
    if len(df) < 120:
        raise NotFoundError(f"Not enough data: {symbol}", code="insufficient_data")
    features = build_feature_frame(df, {symbol: df}, pair_symbol=symbol)
    ref = features.iloc[:-60].drop(columns=["timestamp", "pair_symbol"], errors="ignore")
    recent = features.iloc[-60:].drop(columns=["timestamp", "pair_symbol"], errors="ignore")
    drift = {}
    for col in ref.columns:
        a = ref[col].dropna().to_numpy()
        b = recent[col].dropna().to_numpy()
        if len(a) >= 20 and len(b) >= 20:
            stat, p = ks_2samp(a, b)
            drift[col] = {"ks_stat": round(float(stat), 4), "p_value": round(float(p), 6)}
    flagged = sorted(
        [c for c, d in drift.items() if d["p_value"] < 0.01], key=lambda c: -drift[c]["ks_stat"]
    )
    return {
        "pair_symbol": symbol,
        "window": "last 60 rows vs everything before",
        "n_features_tested": len(drift),
        "drifted_features": flagged[:15],
        "details": drift,
        "stale": find_stale(df),
        "advice": (
            "If core features drift significantly, prefer retraining on recent data; "
            "drift here is descriptive, not automatic retraining."
        ),
    }
