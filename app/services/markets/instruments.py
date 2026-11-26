"""Instrument registry for the gold/dollar market layer (addendum A).

Every instrument declares: id, display names (FA/EN), unit spec, market
("global" | "iran"), official-vs-unofficial flag, and which feature switch
gates it (``MARKET_GLOBAL_ENABLED`` / ``MARKET_IRAN_ENABLED``).

Iran-market instruments are ALWAYS labelled "unofficial market quote"
(gheymate gheir-e rasmi) in the UI — non-negotiable.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.units import UnitSpec


@dataclass(frozen=True)
class Instrument:
    id: str
    name_en: str
    name_fa: str
    unit: UnitSpec
    market: str  # "global" | "iran"
    kind: str  # "fx" | "metal" | "equity" | "vol" | "crypto" | "yield" | "commodity" | "derived"
    unofficial: bool = False  # Iran market quotes -> always True for market prices
    in_dollar_basket: bool = False
    is_driver: bool = False
    notes: str = ""

    @property
    def switch(self) -> str:
        return "MARKET_GLOBAL_ENABLED" if self.market == "global" else "MARKET_IRAN_ENABLED"


_UNIT = UnitSpec("USD", "unit")
_IRR_RIAL = UnitSpec("IRR", "unit")
_IRR_GRAM = UnitSpec("IRR", "gram")
_IRR_COIN_FULL = UnitSpec("IRR", "coin_full")
_IRR_COIN_HALF = UnitSpec("IRR", "coin_half")
_IRR_COIN_QTR = UnitSpec("IRR", "coin_quarter")

INSTRUMENTS: dict[str, Instrument] = {
    i.id: i
    for i in [
        # ---- core ----
        Instrument(
            "XAU_USD",
            "Gold (XAU/USD)",
            "طلا (XAU/USD)",
            _UNIT,
            "global",
            "metal",
            notes="Troy ounce; gram/coin views are derived via app.services.units.",
        ),
        Instrument(
            "USD_IRR_FREE",
            "USD/IRR (free market)",
            "دلار / ریال (بازار آزاد)",
            _IRR_RIAL,
            "iran",
            "fx",
            unofficial=True,
            notes="Unofficial market quote — always labelled.",
        ),
        Instrument(
            "USD_IRR_OFFICIAL",
            "USD/IRR (official rate)",
            "دلار / ریال (نرخ رسمی)",
            _IRR_RIAL,
            "iran",
            "fx",
            unofficial=True,
            notes="Official/exchange-rate (NIMA/central bank) figures — unofficial scrape label retained per policy.",
        ),
        Instrument(
            "GOLD18_IRR",
            "18k gold, per gram (Iran)",
            "طلای ۱۸ عیار، هر گرم",
            _IRR_GRAM,
            "iran",
            "metal",
            unofficial=True,
        ),
        Instrument(
            "COIN_EMAMI_IRR",
            "Emami coin (full)",
            "سکه امامی (تمام)",
            _IRR_COIN_FULL,
            "iran",
            "metal",
            unofficial=True,
        ),
        Instrument(
            "COIN_HALF_IRR", "Half coin", "نیم‌سکه", _IRR_COIN_HALF, "iran", "metal", unofficial=True
        ),
        Instrument(
            "COIN_QUARTER_IRR",
            "Quarter coin",
            "ربع‌سکه",
            _IRR_COIN_QTR,
            "iran",
            "metal",
            unofficial=True,
        ),
        Instrument(
            "USDT_IRT",
            "USDT/IRT (crypto exchange)",
            "تتر / تومان (صرافی)",
            UnitSpec("TOMAN", "unit"),
            "iran",
            "crypto",
            unofficial=True,
            notes="Source: a legitimate crypto exchange public API — many Iranian exchanges block non-IR IPs.",
        ),
        # ---- dollar basket ----
        Instrument(
            "EUR_USD", "EUR/USD", "یورو / دلار", _UNIT, "global", "fx", in_dollar_basket=True
        ),
        Instrument(
            "GBP_USD", "GBP/USD", "پوند / دلار", _UNIT, "global", "fx", in_dollar_basket=True
        ),
        Instrument("USD_JPY", "USD/JPY", "دلار / ین", _UNIT, "global", "fx", in_dollar_basket=True),
        Instrument(
            "USD_CHF", "USD/CHF", "دلار / فرانک", _UNIT, "global", "fx", in_dollar_basket=True
        ),
        Instrument(
            "USD_CAD", "USD/CAD", "دلار / دلار کانادا", _UNIT, "global", "fx", in_dollar_basket=True
        ),
        Instrument(
            "AUD_USD",
            "AUD/USD",
            "دلار استرالیا / دلار",
            _UNIT,
            "global",
            "fx",
            in_dollar_basket=True,
        ),
        Instrument(
            "DXY_STYLE_BASKET",
            "Dollar index (computed basket)",
            "شاخص دلار (محاسبه‌شده)",
            UnitSpec("INDEX", "unit"),
            "global",
            "derived",
            notes="Geometric trade-weighted-style basket computed from the 6 pairs; "
            "NOT the official ICE U.S. Dollar Index (different weights).",
        ),
        # ---- drivers ----
        Instrument(
            "US10Y_REAL",
            "US 10Y real yield (TIPS)",
            "بازده واقعی ۱۰ ساله خزانه‌داری آمریکا",
            UnitSpec("PCT", "unit"),
            "global",
            "yield",
            is_driver=True,
        ),
        Instrument(
            "US10Y_NOMINAL",
            "US 10Y nominal yield",
            "بازده اسمی ۱۰ ساله",
            UnitSpec("PCT", "unit"),
            "global",
            "yield",
            is_driver=True,
        ),
        Instrument(
            "BRENT", "Brent crude", "نفت برنت", _UNIT, "global", "commodity", is_driver=True
        ),
        Instrument("WTI", "WTI crude", "نفت WTI", _UNIT, "global", "commodity", is_driver=True),
        Instrument(
            "SP500",
            "S&P 500",
            "اس اند پی ۵۰۰",
            UnitSpec("INDEX", "unit"),
            "global",
            "equity",
            is_driver=True,
        ),
        Instrument(
            "VIX",
            "CBOE VIX",
            "شاخص نوسان (VIX)",
            UnitSpec("INDEX", "unit"),
            "global",
            "vol",
            is_driver=True,
        ),
        Instrument(
            "XAG_USD",
            "Silver (XAG/USD)",
            "نقره (XAG/USD)",
            _UNIT,
            "global",
            "metal",
            is_driver=True,
        ),
        Instrument("BTC_USD", "Bitcoin", "بیت‌کوین", _UNIT, "global", "crypto", is_driver=True),
    ]
}


def instruments_for(market: str) -> list[Instrument]:
    return [i for i in INSTRUMENTS.values() if i.market == market]


def dollar_basket_members() -> list[Instrument]:
    return [i for i in INSTRUMENTS.values() if i.in_dollar_basket]


def driver_instruments() -> list[Instrument]:
    return [i for i in INSTRUMENTS.values() if i.is_driver]
