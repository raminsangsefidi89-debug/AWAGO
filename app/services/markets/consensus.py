"""Multi-source price consensus (addendum A).

Policy: median + MAD-based outlier rejection. Disagreement between sources
is ALWAYS exposed (per-source values + dispersion); it is never hidden or
silently smoothed away.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class SourceQuote:
    source: str
    value: float
    as_of: str  # ISO UTC
    verified_live: bool = False


@dataclass(frozen=True)
class Consensus:
    value: float | None
    sources_used: list[str]
    sources_rejected: list[str]
    values: dict[str, float]
    dispersion_pct: float | None  # (max-min)/median among used sources
    n_sources: int
    note: str


def _mad(values: Sequence[float]) -> float:
    med = median(values)
    return median([abs(v - med) for v in values])


def consensus_price(quotes: Sequence[SourceQuote], mad_k: float = 3.0) -> Consensus:
    """Median consensus with MAD outlier rejection.

    With < 3 sources MAD rejection is unreliable; in that case all values
    are used and the small sample is stated in the note (fail-soft).
    """
    vals = {q.source: float(q.value) for q in quotes if math.isfinite(q.value)}
    if not vals:
        return Consensus(None, [], [], {}, None, 0, "no sources")
    items = list(vals.items())
    values = [v for _, v in items]
    if len(values) >= 3:
        med = median(values)
        mad = _mad(values)
        scale = 1.4826 * mad if mad > 0 else 0.0
        used = {s: v for s, v in items if scale == 0.0 or abs(v - med) <= mad_k * scale}
        rejected = [s for s, _ in items if s not in used]
    else:
        used = vals
        rejected = []
    if not used:  # pathological: all rejected -> keep median source
        med_s = min(items, key=lambda kv: abs(kv[1] - median(values)))[0]
        used = {med_s: vals[med_s]}
        rejected = [s for s in vals if s != med_s]
    used_vals = list(used.values())
    med_final = median(used_vals)
    spread = (
        (max(used_vals) - min(used_vals)) / med_final * 100.0
        if med_final and len(used_vals) >= 2
        else 0.0
    )
    note = f"consensus of {len(used_vals)} source(s); disagreement {spread:.2f}%" + (
        "; small sample — MAD rejection skipped" if len(values) < 3 else ""
    )
    return Consensus(
        value=float(med_final),
        sources_used=sorted(used),
        sources_rejected=sorted(rejected),
        values=vals,
        dispersion_pct=float(spread),
        n_sources=len(used_vals),
        note=note,
    )
