"""Leakage-audit harness.

Two mechanical audits, run per feature set (and reused per model in Phase 8):

1. **Perturb-future**: modify every bar after a cutoff date and recompute
   features. Rows at or before the cutoff must be bit-identical. Any change
   means the builder peeks into the future.

2. **Suspicious correlation**: compare each feature's correlation with the
   target at leads -k..+k. A feature whose |corr| with the target is ~1.0
   almost certainly *contains* the target (copy leak). A feature that
   correlates far more strongly with *past* returns than with future returns
   at any forward lead is fine (that is information), but a feature whose
   strongest correlation is at a NEGATIVE lead while near-zero at positive
   leads is flagged as "likely derived from realized outcomes" for review.

The harness is honest about what it cannot prove: passing these audits does
not prove the absence of leakage (for example, leakage introduced by data
collection or by a target computed across the split boundary is out of its
reach — the walk-forward splitter with purging/embargo covers that side).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class LeakageAuditResult:
    passed: bool
    perturb_future: dict
    suspicious_correlation: dict

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "perturb_future": self.perturb_future,
            "suspicious_correlation": self.suspicious_correlation,
        }


def audit_perturb_future(
    bars: pd.DataFrame,
    build_fn: Callable[[pd.DataFrame], pd.DataFrame],
    cutoff_index: int | None = None,
    seed: int = 7,
) -> dict:
    """Perturb all bars after the cutoff; features before it must not move."""
    n = len(bars)
    if n < 30:
        return {
            "passed": True,
            "checked_rows": n,
            "changed_rows": 0,
            "note": "series too short to audit",
        }
    cut = cutoff_index if cutoff_index is not None else n // 2

    before = build_fn(bars.copy())

    rng = np.random.default_rng(seed)
    perturbed = bars.copy().reset_index(drop=True)
    tail = perturbed.iloc[cut:]
    factor = np.exp(rng.normal(0.0, 0.05, size=len(tail)))
    for col in ("open", "high", "low", "close"):
        if col in perturbed.columns:
            perturbed.loc[perturbed.index[cut:], col] = tail[col].to_numpy() * factor
    after = build_fn(perturbed)

    cols = [c for c in before.columns if c not in ("timestamp", "pair_symbol")]
    b = before[cols].iloc[:cut]
    a = after[cols].iloc[:cut]
    changed = int((~(b.eq(a) | (b.isna() & a.isna()))).any(axis=1).sum())
    return {
        "passed": changed == 0,
        "checked_rows": int(cut),
        "changed_rows": changed,
        "cutoff_index": int(cut),
    }


def audit_suspicious_correlation(
    features: pd.DataFrame,
    target: pd.Series,
    threshold: float = 0.99,
    leads: range = range(-5, 6),
) -> dict:
    """Flag feature/target correlations that smell like a copy or a leak."""
    merged = features.copy()
    merged["__target__"] = target.to_numpy()
    flags: list[dict] = []
    report: dict[str, dict] = {}
    for col in features.columns:
        if col in ("timestamp", "pair_symbol"):
            continue
        col_report = {"max_abs_corr": 0.0, "lead_of_max": 0}
        for lead in leads:
            shifted = merged["__target__"].shift(-lead) if lead != 0 else merged["__target__"]
            pair = pd.concat([merged[col], shifted], axis=1).dropna()
            if len(pair) < 30 or pair.iloc[:, 0].std() == 0:
                continue
            corr = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
            if abs(corr) > col_report["max_abs_corr"]:
                col_report["max_abs_corr"] = abs(corr)
                col_report["lead_of_max"] = int(lead)
        report[col] = col_report
        if col_report["max_abs_corr"] >= threshold:
            flags.append(
                {
                    "feature": col,
                    "reason": f"|corr| ~ {col_report['max_abs_corr']:.3f} with target (possible copy)",
                }
            )
    return {
        "passed": len(flags) == 0,
        "flagged": flags,
        "per_feature": report,
        "threshold": threshold,
        "caveat": (
            "Passing does not prove absence of leakage; it only rules out "
            "the obvious mechanical patterns this harness can see."
        ),
    }


def run_leakage_audit(
    bars: pd.DataFrame,
    feature_frame: pd.DataFrame,
    target: pd.Series,
    build_fn: Callable[[pd.DataFrame], pd.DataFrame],
) -> LeakageAuditResult:
    pf = audit_perturb_future(bars, build_fn)
    sc = audit_suspicious_correlation(feature_frame, target)
    return LeakageAuditResult(
        passed=pf["passed"] and sc["passed"], perturb_future=pf, suspicious_correlation=sc
    )
