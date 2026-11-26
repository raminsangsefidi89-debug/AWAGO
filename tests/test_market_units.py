"""Unit / calendar / derived-series / consensus tests (addendum A, P0)."""

from __future__ import annotations

from datetime import date

import pytest

from app.services import units
from app.services.calendar_iran import (
    expected_trading_days,
    is_trading_day,
    is_weekend,
    tehran_now,
)
from app.services.jalali import jalali_to_gregorian
from app.services.markets import derived
from app.services.markets.consensus import SourceQuote, consensus_price
from app.services.markets.instruments import (
    INSTRUMENTS,
    dollar_basket_members,
    driver_instruments,
    instruments_for,
)


# ------------------------------ units --------------------------------------
class TestUnits:
    def test_toman_rial_roundtrip(self):
        assert units.to_rial(1000, "TOMAN") == 10000
        assert units.from_rial(10000, "TOMAN") == 1000
        assert units.to_rial(10000, "IRR") == 10000

    def test_rejects_cross_currency(self):
        with pytest.raises(units.UnitError):
            units.to_rial(1.0, "USD")

    def test_ounce_gram_roundtrip(self):
        g = units.to_grams(2.0, "ounce")
        assert g == pytest.approx(62.207)
        assert units.from_grams(g, "ounce") == pytest.approx(2.0)

    def test_coin_fine_gold(self):
        assert units.coin_fine_gold_g("coin_full") == pytest.approx(7.3224)
        assert units.coin_fine_gold_g("coin_half") == pytest.approx(3.6612)
        assert units.coin_fine_gold_g("coin_quarter") == pytest.approx(1.8306)
        with pytest.raises(units.UnitError):
            units.coin_fine_gold_g("coin_bahar")

    def test_display_value(self):
        v, u = units.display_value(100000, units.UnitSpec("IRR", "unit"), prefer_toman=True)
        assert (v, u.currency) == (10000, "TOMAN")
        v2, u2 = units.display_value(100000, units.UnitSpec("IRR", "unit"), prefer_toman=False)
        assert (v2, u2.currency) == (100000, "IRR")

    def test_unit_labels_fa(self):
        assert "ریال" in units.UnitSpec("IRR", "gram").label_fa()
        assert "سکه تمام" in units.UnitSpec("IRR", "coin_full").label_fa()


# ------------------------------ calendar -----------------------------------
class TestIranCalendar:
    def test_tehran_offset(self):
        from datetime import datetime, timezone

        noon = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
        assert tehran_now(noon).hour == 15  # +3:30
        assert tehran_now(noon).minute == 30

    def test_weekend_thu_fri(self):
        # 2026-11-26 is Thursday; 27 is Friday
        assert is_weekend(date(2026, 11, 26))
        assert is_weekend(date(2026, 11, 27))
        assert not is_weekend(date(2026, 11, 28))  # Saturday = trading day

    def test_trading_day_with_holidays(self):
        holi = [date(2026, 3, 21)]  # Noruz 1405-01-01 falls 2026-03-21
        assert not is_trading_day(date(2026, 3, 21), holidays=holi)
        assert is_trading_day(date(2026, 3, 22), holidays=holi)

    def test_expected_trading_days_weekends_excluded(self):
        days = expected_trading_days(date(2026, 11, 21), date(2026, 11, 28))  # Sat..Sat
        assert len(days) == 6  # both Saturdays + Sun..Wed
        assert date(2026, 11, 26) not in days  # Thursday
        assert date(2026, 11, 27) not in days  # Friday

    def test_noruz_fixed_holiday_matches_jalali(self):
        g = jalali_to_gregorian(1405, 1, 1)
        assert g == (2026, 3, 21)


# ------------------------------ derived ------------------------------------
class TestDerived:
    def test_implied_gram_formula(self):
        # $100/oz, 5,000,000 IRR/$ -> 100*5e6/31.1035 = 16,075,361.29 per gram
        v = derived.implied_gram_irr(100.0, 5_000_000.0)
        assert v == pytest.approx(16_075_361.29, rel=1e-6)
        assert derived.implied_gram_irr_18k(100.0, 5_000_000.0) == pytest.approx(v * 0.75)

    def test_coin_intrinsic_and_bubble(self):
        intr = derived.coin_intrinsic_irr("coin_full", 100.0, 5_000_000.0)
        assert intr == pytest.approx(derived.implied_gram_irr(100.0, 5e6) * 7.3224)
        b = derived.coin_bubble_irr("coin_full", intr * 1.2, 100.0, 5_000_000.0)
        assert b["bubble_irr"] == pytest.approx(intr * 0.2)
        assert b["bubble_pct"] == pytest.approx(20.0)

    def test_usd_gap(self):
        g = derived.usd_gap(600_000, 420_000)
        assert g["gap_irr"] == 180_000
        assert g["gap_pct"] == pytest.approx(180_000 / 420_000 * 100)

    def test_cross_market_check_warns_but_never_corrects(self):
        implied = derived.implied_gram_irr_18k(100.0, 5e6)
        res = derived.cross_market_check(implied * 1.3, 100.0, 5e6)
        assert res["status"] == "warning"
        assert res["market_irr"] == pytest.approx(implied * 1.3)  # untouched
        ok = derived.cross_market_check(implied * 1.05, 100.0, 5e6)
        assert ok["status"] == "ok"


# ------------------------------ consensus ----------------------------------
class TestConsensus:
    def test_median_and_outlier_rejection(self):
        q = [
            SourceQuote("a", 100.0, "2026-11-26T00:00:00Z"),
            SourceQuote("b", 101.0, "2026-11-26T00:00:00Z"),
            SourceQuote("c", 99.0, "2026-11-26T00:00:00Z"),
            SourceQuote("d", 250.0, "2026-11-26T00:00:00Z"),  # clear outlier
        ]
        c = consensus_price(q)
        assert c.value == pytest.approx(100.0)
        assert "d" in c.sources_rejected
        assert c.n_sources == 3
        assert c.dispersion_pct is not None and c.dispersion_pct < 5

    def test_small_sample_fails_soft(self):
        c = consensus_price([SourceQuote("a", 10.0, "t"), SourceQuote("b", 11.0, "t")])
        assert c.n_sources == 2
        assert "small sample" in c.note
        assert c.value == pytest.approx(10.5)

    def test_empty(self):
        c = consensus_price([])
        assert c.value is None

    def test_disagreement_always_exposed(self):
        c = consensus_price([SourceQuote("a", 100.0, "t"), SourceQuote("b", 130.0, "t")])
        assert c.values == {"a": 100.0, "b": 130.0}
        assert c.dispersion_pct > 20


# ------------------------------ instruments --------------------------------
class TestInstruments:
    def test_iran_market_all_unofficial(self):
        for inst in instruments_for("iran"):
            assert inst.unofficial, inst.id

    def test_switches(self):
        assert INSTRUMENTS["XAU_USD"].switch == "MARKET_GLOBAL_ENABLED"
        assert INSTRUMENTS["USD_IRR_FREE"].switch == "MARKET_IRAN_ENABLED"

    def test_basket_and_drivers(self):
        assert len(dollar_basket_members()) == 6
        assert len(driver_instruments()) >= 8

    def test_units_explicit_everywhere(self):
        for inst in INSTRUMENTS.values():
            assert inst.unit.currency and inst.unit.quantity
