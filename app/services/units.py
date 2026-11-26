"""Canonical unit handling: currency (rial/toman) and quantity (oz/g/coin).

HARD RULES (addendum A):
* Every stored series carries an explicit unit pair
  (``UnitSpec``) — units are never mixed silently.
* All conversions go through this module only; it is fully unit-tested.
* Canonical storage unit for IRR money values is RIAL; toman is a display
  unit (1 toman = 10 rial — the common-market convention).
* Canonical storage for gold weight is GRAMS of fine gold; ounces convert
  via 1 troy ounce = 31.1035 grams.
"""

from __future__ import annotations

from dataclasses import dataclass

TROY_OUNCE_GRAMS = 31.1035
TOMAN_RIAL = 10

# Purity factors (fine gold fraction). Documented assumptions:
# * 18k gold = 750/1000 fine (standard 18-karat).
# * Emami (Imami) full coin: 8.136 g gross at 900/1000 -> 7.3224 g fine gold.
#   Half = 4.068 g, quarter = 2.034 g gross at the same fineness.
PURITY_18K = 0.750
PURITY_COIN_900 = 0.900
EMAMI_FULL_GROSS_G = 8.136
EMAMI_HALF_GROSS_G = 4.068
EMAMI_QUARTER_GROSS_G = 2.034
EMAMI_FINE_G = EMAMI_FULL_GROSS_G * PURITY_COIN_900  # 7.3224 g fine


class UnitError(ValueError):
    """Raised for unknown or incompatible units."""


@dataclass(frozen=True)
class UnitSpec:
    """Explicit unit of a series value."""

    currency: str  # "IRR" | "TOMAN" | "USD" | ...
    quantity: str  # "unit" | "gram" | "ounce" | "coin_full" | "coin_half" | "coin_quarter"

    def as_dict(self) -> dict:
        return {"currency": self.currency, "quantity": self.quantity}

    def label_fa(self) -> str:
        cur = {"IRR": "ریال", "TOMAN": "تومان", "USD": "دلار"}.get(self.currency, self.currency)
        qty = {
            "unit": "",
            "gram": "/ گرم",
            "ounce": "/ اونس",
            "coin_full": "/ سکه تمام",
            "coin_half": "/ نیم‌سکه",
            "coin_quarter": "/ ربع‌سکه",
        }.get(self.quantity, "/" + self.quantity)
        return f"{cur}{qty}"


def to_rial(value: float, currency: str) -> float:
    """Convert a money amount to rial (canonical)."""
    c = currency.upper()
    if c == "IRR":
        return float(value)
    if c == "TOMAN":
        return float(value) * TOMAN_RIAL
    raise UnitError(f"Cannot convert {currency!r} to IRR — cross-currency needs an FX rate")


def from_rial(value_rial: float, currency: str) -> float:
    c = currency.upper()
    if c == "IRR":
        return float(value_rial)
    if c == "TOMAN":
        return float(value_rial) / TOMAN_RIAL
    raise UnitError(f"Cannot convert IRR to {currency!r} — cross-currency needs an FX rate")


def to_grams(value: float, quantity: str) -> float:
    """Convert a gold weight to grams (gross weight unless noted)."""
    q = quantity.lower()
    if q == "gram":
        return float(value)
    if q == "ounce":
        return float(value) * TROY_OUNCE_GRAMS
    raise UnitError(
        f"Unknown weight unit: {quantity!r} (coins have fixed weights — use coin helpers)"
    )


def from_grams(value_g: float, quantity: str) -> float:
    q = quantity.lower()
    if q == "gram":
        return float(value_g)
    if q == "ounce":
        return float(value_g) / TROY_OUNCE_GRAMS
    raise UnitError(f"Unknown weight unit: {quantity!r}")


def coin_fine_gold_g(coin: str) -> float:
    """Fine gold content (grams) of an Iranian coin type."""
    table = {
        "coin_full": EMAMI_FINE_G,
        "coin_half": EMAMI_HALF_GROSS_G * PURITY_COIN_900,
        "coin_quarter": EMAMI_QUARTER_GROSS_G * PURITY_COIN_900,
    }
    if coin not in table:
        raise UnitError(f"Unknown coin type: {coin!r}")
    return table[coin]


def display_value(value_rial: float, unit: UnitSpec, prefer_toman: bool) -> tuple[float, UnitSpec]:
    """Convert a canonical IRR value for display. Returns (value, unit)."""
    if unit.currency not in ("IRR", "TOMAN"):
        return value_rial, unit
    if prefer_toman:
        return from_rial(value_rial, "TOMAN"), UnitSpec("TOMAN", unit.quantity)
    return to_rial(value_rial, "IRR"), UnitSpec("IRR", unit.quantity)
