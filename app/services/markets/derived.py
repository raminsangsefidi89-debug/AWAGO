"""Derived market series (addendum A). All formulas documented + unit-tested.

Formulas (documented assumptions — spec + standard market conventions):

1. Implied global gold value per gram in IRR (cross-market reference):
       implied_gram_irr = (XAU_USD  [USD/oz]) * (USD_IRR_FREE [IRR/USD])
                          / 31.1035  [g/oz]
   (fine gold, 24k). For 18k: multiply by 0.750.
2. Implied Emami coin intrinsic (IRR):
       coin_intrinsic_irr = implied_gram_irr * 7.3224
   (8.136 g gross * 900/1000 fine = 7.3224 g fine gold; half/quarter scale
   proportionally by their fine-gold content.)
3. Coin bubble (حباب سکه):
       bubble_irr  = coin_market_irr - coin_intrinsic_irr
       bubble_pct  = bubble_irr / coin_intrinsic_irr * 100
4. Official/free USD gap:
       gap_abs = free - official            [IRR]
       gap_pct = (free - official)/official * 100
5. Cross-market consistency: compare local 18k gram quote vs implied 18k
   gram. A deviation beyond a threshold raises a QUALITY WARNING — it is
   surfaced, never silently "corrected".

Rial/toman: everything is computed in RIAL (canonical); toman is display.
"""

from __future__ import annotations

from app.services.units import (
    PURITY_18K,
    TROY_OUNCE_GRAMS,
    coin_fine_gold_g,
    to_rial,
)

CROSS_MARKET_WARN_PCT = 10.0  # deviation threshold that raises a warning


def implied_gram_irr(xau_usd: float, usd_irr_free: float) -> float:
    """Implied fine-gold (24k) value per gram in IRR from global markets."""
    return float(xau_usd) * float(usd_irr_free) / TROY_OUNCE_GRAMS


def implied_gram_irr_18k(xau_usd: float, usd_irr_free: float) -> float:
    return implied_gram_irr(xau_usd, usd_irr_free) * PURITY_18K


def coin_intrinsic_irr(coin: str, xau_usd: float, usd_irr_free: float) -> float:
    """Intrinsic (fine-gold) value of an Iranian coin in IRR."""
    return implied_gram_irr(xau_usd, usd_irr_free) * coin_fine_gold_g(coin)


def coin_bubble_irr(
    coin: str, coin_market_irr: float, xau_usd: float, usd_irr_free: float
) -> dict[str, float]:
    intrinsic = coin_intrinsic_irr(coin, xau_usd, usd_irr_free)
    bubble = float(coin_market_irr) - intrinsic
    pct = (bubble / intrinsic * 100.0) if intrinsic else float("nan")
    return {"intrinsic_irr": intrinsic, "bubble_irr": bubble, "bubble_pct": pct}


def usd_gap(free_irr: float, official_irr: float) -> dict[str, float]:
    free = to_rial(free_irr, "IRR")
    official = to_rial(official_irr, "IRR")
    gap = free - official
    pct = (gap / official * 100.0) if official else float("nan")
    return {"gap_irr": gap, "gap_pct": pct}


def cross_market_check(
    gold18_market_irr: float, xau_usd: float, usd_irr_free: float
) -> dict[str, float | str]:
    """Compare local 18k gram price with the implied cross-market value.

    Returns a verdict dict. NEVER auto-corrects; deviations are warnings.
    """
    implied = implied_gram_irr_18k(xau_usd, usd_irr_free)
    if implied <= 0:
        return {"status": "insufficient_data", "implied_irr": implied}
    dev_pct = (float(gold18_market_irr) - implied) / implied * 100.0
    status = "ok" if abs(dev_pct) <= CROSS_MARKET_WARN_PCT else "warning"
    return {
        "status": status,
        "implied_irr": implied,
        "market_irr": float(gold18_market_irr),
        "deviation_pct": dev_pct,
        "threshold_pct": CROSS_MARKET_WARN_PCT,
        "note": (
            "اختلاف قیمت محلی با ارزش ضمنی جهانی — هشدار کیفیت (اصلاح خودکار انجام نمی‌شود)"
            if status == "warning"
            else "سازگار با ارزش ضمنی جهانی"
        ),
    }
