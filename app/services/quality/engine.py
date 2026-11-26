"""Data-quality engine: gaps, staleness, outliers, OHLC sanity, cross-rates.

Every check is pure pandas/numpy and returns JSON-safe findings. The engine
is honest about applicability: triangular cross-rate checks run only on
real, same-source legs (independent synthetic walks would fail them
meaninglessly), and each report states what was and was not applicable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.logging_config import get_logger

logger = get_logger(__name__)

QUALITY_SCHEMA_VERSION = "1"


def _round(value: Any, nd: int = 6) -> Any:
    if value is None:
        return None
    try:
        if not np.isfinite(float(value)):
            return None
        return round(float(value), nd)
    except (TypeError, ValueError):
        return None


def infer_cadence(timestamps: pd.Series) -> str:
    """'business_day' when weekends are mostly absent, else 'calendar_day'."""
    ts = pd.to_datetime(timestamps)
    if len(ts) < 14:
        return "calendar_day"
    dow = ts.dt.dayofweek if not hasattr(ts.dt, "day_of_week") else ts.dt.day_of_week
    weekend_share = float((dow >= 5).mean())
    return "business_day" if weekend_share < 0.2 else "calendar_day"


def find_gaps(df: pd.DataFrame, max_report: int = 25) -> dict[str, Any]:
    """Missing expected trading days given the inferred cadence."""
    if len(df) < 2:
        return {"cadence": "unknown", "missing_days": [], "missing_count": 0}
    ts = pd.to_datetime(df["timestamp"]).sort_values()
    cadence = infer_cadence(ts)
    full = pd.date_range(ts.iloc[0], ts.iloc[-1], freq="D")
    if cadence == "business_day":
        full = full[full.dayofweek < 5]
    present = set(ts.dt.date)
    missing = [d.date().isoformat() for d in full if d.date() not in present]
    return {
        "cadence": cadence,
        "missing_count": len(missing),
        "missing_days": missing[:max_report],
    }


def find_stale(df: pd.DataFrame, now: datetime | None = None) -> dict[str, Any]:
    """Staleness of the newest bar (calendar days behind 'now')."""
    if len(df) == 0:
        return {"is_stale": True, "days_behind": None, "latest": None}
    now = now or datetime.now(timezone.utc)
    latest = pd.to_datetime(df["timestamp"]).max()
    latest_naive = (
        latest.tz_localize(None)
        if latest.tzinfo is None
        else latest.tz_convert("UTC").tz_localize(None)
    )
    days_behind = (now.replace(tzinfo=None) - latest_naive).days
    return {
        "is_stale": days_behind > 3,
        "days_behind": int(days_behind),
        "latest": latest.isoformat(),
    }


def find_outliers(
    df: pd.DataFrame, window: int = 10, threshold: float = 3.5, max_report: int = 25
) -> dict[str, Any]:
    """Hampel-style outlier detection on log returns (robust z-score)."""
    if len(df) < window + 2:
        return {"outlier_count": 0, "outliers": [], "method": "hampel_log_returns"}
    close = pd.to_numeric(df["close"]).astype(float)
    rets = np.log(close / close.shift(1))
    med = rets.rolling(window, min_periods=window, center=True).median()
    mad = (rets - med).abs().rolling(window, min_periods=window, center=True).median()
    robust_z = 0.6745 * (rets - med) / mad.replace(0.0, np.nan)
    flagged = robust_z.abs() > threshold
    idx = np.where(flagged.fillna(False).to_numpy())[0]
    outliers = [
        {
            "timestamp": pd.to_datetime(df["timestamp"]).iloc[i].isoformat(),
            "close": _round(close.iloc[i]),
            "log_return": _round(rets.iloc[i]),
            "robust_z": _round(robust_z.iloc[i], 2),
        }
        for i in idx[:max_report]
    ]
    return {"outlier_count": len(idx), "outliers": outliers, "method": "hampel_log_returns"}


def validate_ohlc(df: pd.DataFrame, max_report: int = 25) -> dict[str, Any]:
    """Schema sanity: positive prices, high >= max(open, close), low <= min(...)."""
    problems: list[str] = []
    bad_rows = 0
    required = {"timestamp", "open", "high", "low", "close"}
    if not required.issubset(df.columns):
        return {
            "valid": False,
            "problems": [f"missing columns: {sorted(required - set(df.columns))}"],
            "bad_rows": 0,
        }
    for i, row in enumerate(df.itertuples()):
        if row.close <= 0 or row.open <= 0 or row.high <= 0 or row.low <= 0:
            bad_rows += 1
            if len(problems) < max_report:
                problems.append(f"row {i}: non-positive price")
        elif row.high + 1e-12 < max(row.open, row.close) or row.low - 1e-12 > min(
            row.open, row.close
        ):
            bad_rows += 1
            if len(problems) < max_report:
                problems.append(
                    f"row {i}: OHLC violated (o={row.open} h={row.high} l={row.low} c={row.close})"
                )
    return {"valid": bad_rows == 0, "problems": problems, "bad_rows": bad_rows}


def triangular_consistency(
    legs: dict[str, pd.DataFrame],
    tolerance: float = 0.005,
    max_report: int = 10,
) -> dict[str, Any]:
    """Cross-rate consistency, e.g. EUR/USD ≈ GBP/USD × EUR/GBP.

    Only meaningful for real data of one source: ``legs`` maps pair symbol ->
    frame. Returns 'not_applicable' when the required legs are missing or
    the series are synthetic (caller passes is_demo).
    """
    needed = ("EUR/USD", "GBP/USD", "EUR/GBP")
    if any(k not in legs or len(legs[k]) == 0 for k in needed):
        return {
            "applicable": False,
            "reason": "required legs (EUR/USD, GBP/USD, EUR/GBP) not all present",
        }
    merged = None
    for k in needed:
        part = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(legs[k]["timestamp"]).dt.date,
                k: pd.to_numeric(legs[k]["close"]).astype(float).to_numpy(),
            }
        )
        merged = part if merged is None else merged.merge(part, on="timestamp", how="inner")
    assert merged is not None
    if len(merged) == 0:
        return {"applicable": False, "reason": "no overlapping dates across legs"}
    implied = merged["GBP/USD"] * merged["EUR/GBP"]
    rel_err = ((merged["EUR/USD"] - implied).abs() / implied).replace([np.inf], np.nan)
    violations = merged.loc[rel_err > tolerance, "timestamp"]
    return {
        "applicable": True,
        "checked_days": len(merged),
        "tolerance": tolerance,
        "violation_count": len(violations),
        "violation_days": [d.isoformat() for d in violations.iloc[:max_report]],
        "max_rel_error": _round(rel_err.max(), 6),
        "median_rel_error": _round(rel_err.median(), 6),
    }


def build_quality_report(
    pair_symbol: str,
    data_source: str,
    df: pd.DataFrame,
    *,
    is_demo: bool = False,
    cross_legs: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """Assemble the full quality report for one series."""
    report: dict[str, Any] = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "pair_symbol": pair_symbol,
        "data_source": data_source,
        "is_demo": is_demo,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(df),
        "gaps": find_gaps(df),
        "stale": find_stale(df),
        "outliers": find_outliers(df),
        "ohlc_validation": validate_ohlc(df),
    }
    if cross_legs is not None and not is_demo:
        report["triangular_consistency"] = triangular_consistency(cross_legs)
    else:
        report["triangular_consistency"] = {
            "applicable": False,
            "reason": "not applicable to demo/synthetic data (independent series)"
            if is_demo
            else "legs not supplied",
        }
    report["summary"] = _summarize(report)
    return report


def _summarize(report: dict[str, Any]) -> dict[str, Any]:
    issues = []
    if report["gaps"].get("missing_count", 0) > 0:
        issues.append(f"{report['gaps']['missing_count']} missing day(s)")
    if report["stale"].get("is_stale"):
        issues.append(f"stale: {report['stale'].get('days_behind')} day(s) behind")
    if report["outliers"].get("outlier_count", 0) > 0:
        issues.append(f"{report['outliers']['outlier_count']} outlier(s)")
    if not report["ohlc_validation"].get("valid", True):
        issues.append(f"{report['ohlc_validation'].get('bad_rows', 0)} invalid OHLC row(s)")
    tri = report.get("triangular_consistency", {})
    if tri.get("applicable") and tri.get("violation_count", 0) > 0:
        issues.append(f"{tri['violation_count']} cross-rate violation(s)")
    return {
        "status": "clean" if not issues else "issues_found",
        "issues": issues,
        "issue_count": len(issues),
    }
