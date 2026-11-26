"""Tests for the Jalali converter (anchor dates + round-trips + formatting)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.jalali import (
    digits_fa,
    format_jalali_fa,
    format_jalali_long_fa,
    gregorian_to_jalali,
    jalali_to_gregorian,
    to_jalali,
)

# Well-known anchors (Nowruz dates, historical dates, millennial boundaries).
ANCHORS = [
    ((2020, 3, 20), (1399, 1, 1)),  # Nowruz 1399
    ((2021, 3, 21), (1400, 1, 1)),  # Nowruz 1400
    ((2024, 3, 20), (1403, 1, 1)),  # Nowruz 1403
    ((2026, 3, 21), (1405, 1, 1)),  # Nowruz 1405
    ((1979, 2, 11), (1357, 11, 22)),  # 22 Bahman 1357
    ((2000, 1, 1), (1378, 10, 11)),
    ((2026, 11, 26), (1405, 9, 5)),
]


class TestConversion:
    @pytest.mark.parametrize(("greg", "jal"), ANCHORS)
    def test_gregorian_to_jalali(self, greg, jal):
        assert gregorian_to_jalali(*greg) == jal

    @pytest.mark.parametrize(("greg", "jal"), ANCHORS)
    def test_jalali_to_gregorian(self, greg, jal):
        assert jalali_to_gregorian(*jal) == greg

    def test_roundtrip_many_days(self):
        d = date(1990, 1, 1)
        for _ in range(4000):
            jy, jm, jd = to_jalali(d)
            back = jalali_to_gregorian(jy, jm, jd)
            assert back == (d.year, d.month, d.day), f"round-trip failed for {d}"
            d += timedelta(days=37)

    def test_jalali_month_bounds(self):
        # 1 Farvardin .. 29/30/31 per month; Esfand has 29 or 30
        assert gregorian_to_jalali(2026, 3, 21) == (1405, 1, 1)
        assert gregorian_to_jalali(2026, 3, 21 + 30)[1] == 1  # still Farvardin (31 days)
        assert gregorian_to_jalali(2026, 3, 21 + 31)[1] == 2  # Ordibehesht


class TestFormatting:
    def test_digits_fa(self):
        assert digits_fa("1405/09/05") == "۱۴۰۵/۰۹/۰۵"

    def test_format_jalali_fa(self):
        assert format_jalali_fa(date(2026, 11, 26)) == "۱۴۰۵/۰۹/۰۵"

    def test_format_jalali_long_fa(self):
        assert format_jalali_long_fa(date(2026, 11, 26)) == "۵ آذر ۱۴۰۵"
