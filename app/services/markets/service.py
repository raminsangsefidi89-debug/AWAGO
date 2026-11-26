"""Market/news service: state assembly for the dashboard (addendum E).

Demo mode: when no live data exists, a deterministic DEMO state is generated
and every panel is badged as demo — cached/demo is NEVER shown as live.
Every price carries (value, unit, source, as_of, age, is_demo, is_unofficial).
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from app.services import units
from app.services.markets import derived
from app.services.markets.consensus import SourceQuote, consensus_price
from app.services.markets.instruments import (
    INSTRUMENTS,
    Instrument,
    driver_instruments,
)

DEMO_ANCHOR = datetime(2026, 11, 26, 8, 0, tzinfo=timezone.utc)
AGE_STALE_MINUTES = 240


def _demo_rng(instr_id: str) -> random.Random:
    return random.Random(f"awago-market-demo/{instr_id}")


_DEMO_BASE = {
    # Anchors are mutually consistent with the derived formulas (documented):
    # implied 24k/g = 4200 × 1.15e6 / 31.1035 ≈ 155.29e6 IRR; 18k ≈ ×0.75;
    # Emami intrinsic = 7.3224 g fine × implied 24k ≈ 1.137e9 IRR.
    "XAU_USD": 4200.0,
    "USD_IRR_FREE": 1_150_000.0,
    "USD_IRR_OFFICIAL": 850_000.0,
    "GOLD18_IRR": 118_800_000.0,
    "COIN_EMAMI_IRR": 1_200_000_000.0,
    "COIN_HALF_IRR": 640_000_000.0,
    "COIN_QUARTER_IRR": 340_000_000.0,
    "USDT_IRT": 118_000.0,
    "EUR_USD": 1.08,
    "GBP_USD": 1.27,
    "USD_JPY": 155.0,
    "USD_CHF": 0.88,
    "USD_CAD": 1.39,
    "AUD_USD": 0.65,
    "US10Y_REAL": 2.1,
    "US10Y_NOMINAL": 4.4,
    "BRENT": 74.5,
    "WTI": 70.2,
    "SP500": 6700.0,
    "VIX": 15.5,
    "XAG_USD": 52.0,
    "BTC_USD": 92_000.0,
}


def _age_minutes(as_of: datetime, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    return (now - as_of).total_seconds() / 60.0


def _basket_demo_value(now: datetime) -> float:
    """Equal-weight geometric dollar index from the 6 demo pairs.

    NOT the official ICE DXY (different weights) — labelled 'computed basket'.
    USD-side pairs (USD/JPY, USD/CHF, USD/CAD) contribute positively,
    others inversely. (Recursion-safe: members are never the basket.)
    """
    import math

    usd_side = {"USD_JPY", "USD_CHF", "USD_CAD"}
    members = [i.id for i in INSTRUMENTS.values() if i.in_dollar_basket]
    log_sum = 0.0
    for mid in members:
        ratio = float(demo_quote(mid, now)["value"]) / _DEMO_BASE[mid]
        log_sum += math.log(ratio) * (1 if mid in usd_side else -1)
    return round(100.0 * math.exp(log_sum / len(members)), 4)


def demo_quote(instr_id: str, now: datetime | None = None) -> dict[str, Any]:
    """One deterministic demo quote (labelled demo — never live)."""
    now = now or datetime.now(timezone.utc)
    rng = _demo_rng(instr_id)
    if instr_id == "DXY_STYLE_BASKET":
        base = _basket_demo_value(now)
    else:
        base = _DEMO_BASE[instr_id]
    jitter = 1.0 + rng.uniform(-0.01, 0.01)
    inst = INSTRUMENTS[instr_id]
    return {
        "instrument": instr_id,
        "name_en": inst.name_en,
        "name_fa": inst.name_fa,
        "value": round(base * jitter, 4),
        "unit": inst.unit.as_dict(),
        "unit_label_fa": inst.unit.label_fa(),
        "as_of": now.isoformat(),
        "age_minutes": round(_age_minutes(now, now), 1),
        "is_demo": True,
        "is_unofficial": inst.unofficial,
        "sources": ["demo"],
        "dispersion_pct": 0.0,
        "verified_live": False,
    }


def _quote_from_consensus(
    instr: Instrument, quotes: list[SourceQuote], is_demo: bool, now: datetime
) -> dict[str, Any]:
    cons = consensus_price(quotes)
    as_of = max((q.as_of for q in quotes), default=now.isoformat())
    try:
        as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError:
        as_of_dt = now
    return {
        "instrument": instr.id,
        "name_en": instr.name_en,
        "name_fa": instr.name_fa,
        "value": cons.value,
        "unit": instr.unit.as_dict(),
        "unit_label_fa": instr.unit.label_fa(),
        "as_of": as_of_dt.isoformat(),
        "age_minutes": round(_age_minutes(as_of_dt, now), 1),
        "is_demo": is_demo,
        "is_unofficial": instr.unofficial,
        "sources": cons.sources_used,
        "sources_rejected": cons.sources_rejected,
        "per_source": cons.values,
        "dispersion_pct": cons.dispersion_pct,
        "consensus_note": cons.note,
        "verified_live": all(q.verified_live for q in quotes) and bool(quotes),
    }


def market_overview(prefer_toman: bool = True, now: datetime | None = None) -> dict[str, Any]:
    """Global + Iran panels with derived series, freshness and quality warnings.

    Demo fallback is explicit: ``data_mode`` field is "demo" and every panel
    carries is_demo=True.
    """
    now = now or datetime.now(timezone.utc)
    quotes = {iid: demo_quote(iid, now) for iid in INSTRUMENTS}

    # ---- derived series (documented formulas, computed, not invented) ----
    xau = float(quotes["XAU_USD"]["value"])
    free = float(quotes["USD_IRR_FREE"]["value"])
    official = float(quotes["USD_IRR_OFFICIAL"]["value"])
    gold18 = float(quotes["GOLD18_IRR"]["value"])
    coin = float(quotes["COIN_EMAMI_IRR"]["value"])

    implied_gram = derived.implied_gram_irr(xau, free)
    bubble = derived.coin_bubble_irr("coin_full", coin, xau, free)
    gap = derived.usd_gap(free, official)
    xcheck = derived.cross_market_check(gold18, xau, free)

    def _disp(val_rial: float) -> tuple[float, str, str]:
        v, u = units.display_value(val_rial, units.UnitSpec("IRR", "unit"), prefer_toman)
        return round(v, 2), u.currency, u.label_fa()

    derived_series = {
        "implied_gram_irr": {
            "value_rial": round(implied_gram, 2),
            "formula": "XAU/USD × USD/IRR ÷ 31.1035",
            "display": _disp(implied_gram),
        },
        "implied_gram_irr_18k": {
            "value_rial": round(implied_gram * units.PURITY_18K, 2),
            "formula": "implied_gram × 0.750",
            "display": _disp(implied_gram * units.PURITY_18K),
        },
        "coin_intrinsic_irr": {
            "value_rial": round(bubble["intrinsic_irr"], 2),
            "formula": "implied_gram × 7.3224 (سکه امامی: 8.136g × 900/1000)",
            "display": _disp(bubble["intrinsic_irr"]),
        },
        "coin_bubble": {
            "bubble_irr": round(bubble["bubble_irr"], 2),
            "bubble_pct": round(bubble["bubble_pct"], 2),
            "display": _disp(bubble["bubble_irr"]),
        },
        "usd_gap": {
            "gap_irr": round(gap["gap_irr"], 2),
            "gap_pct": round(gap["gap_pct"], 2),
            "display": _disp(gap["gap_irr"]),
        },
    }

    warnings = []
    if xcheck["status"] == "warning":
        warnings.append(
            {
                "type": "cross_market",
                "message": xcheck["note"],
                "deviation_pct": round(float(xcheck["deviation_pct"]), 2),
            }
        )
    stale = [qid for qid, q in quotes.items() if float(q["age_minutes"]) > AGE_STALE_MINUTES]
    if stale:
        warnings.append({"type": "stale", "message": "داده‌های قدیمی (stale): " + ", ".join(stale)})

    basket_members = [quotes[i.id] for i in INSTRUMENTS.values() if i.in_dollar_basket]
    drivers = [quotes[i.id] for i in driver_instruments()]

    return {
        "data_mode": "demo",  # demo state — never presented as live
        "generated_at": now.isoformat(),
        "global": {
            "gold": quotes["XAU_USD"],
            "dollar_index": quotes["DXY_STYLE_BASKET"],
            "basket": basket_members,
            "drivers": drivers,
        },
        "iran": {
            "usd_free": quotes["USD_IRR_FREE"],
            "usd_official": quotes["USD_IRR_OFFICIAL"],
            "gold18": quotes["GOLD18_IRR"],
            "coin_full": quotes["COIN_EMAMI_IRR"],
            "coin_half": quotes["COIN_HALF_IRR"],
            "coin_quarter": quotes["COIN_QUARTER_IRR"],
            "usdt": quotes["USDT_IRT"],
            "unofficial_badge": "قیمت بازار غیررسمی (unofficial market quote)",
        },
        "derived": derived_series,
        "cross_market": xcheck,
        "warnings": warnings,
        "units": {
            "currency_display": "TOMAN" if prefer_toman else "IRR",
            "weight_note": "همه مقادیر طلا بر حسب گرم یا اونس (31.1035 گرم) با برچسب صریح",
        },
    }
