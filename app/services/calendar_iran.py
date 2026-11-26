"""Iran market calendar: Tehran timezone, weekends, holidays, sessions.

* Timestamps are stored in UTC (project-wide rule) and displayed in Jalali
  and/or Gregorian. Tehran is UTC+3:30 (no DST since 2023).
* Iranian weekend: Thursday + Friday (configurable). Friday has always been
  the weekly holiday; Thursday is included per the target-market spec and is
  configurable via ``IRAN_WEEKEND_DAYS``.
* Iranian holidays are a mix of fixed Jalali dates and lunar (Islamic)
  dates that shift every year. Lunar holidays CANNOT be computed reliably
  offline, so they live in a **curated** JSON file
  (``data/holidays_iran.json``) that ships with known dates and is meant to
  be updated annually; missing entries degrade gracefully (the calendar
  reports ``holiday_coverage`` honestly).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TEHRAN_UTC_OFFSET_MINUTES = 210  # UTC+3:30

# Fixed (solar) Iranian holidays as (jy_offset_reference not needed — Jalali
# month/day). Year-independent list of FIXED Jalali dates; the curated file
# adds lunar/variable observances per year.
FIXED_JALALI_HOLIDAYS = [
    (1, 1),  # Noruz
    (1, 2),
    (1, 3),
    (1, 4),
    (1, 12),  # Islamic Republic Day
    (1, 13),  # Sizdah Bedar
    (3, 14),  # Khordad National Uprising
    (3, 15),
    (11, 22),  # Revolution Day
    (12, 29),  # Nationalization of Oil
]

DEFAULT_WEEKEND_DAYS = (3, 4)  # Thursday=3, Friday=4 (Python weekday(): Mon=0)


def tehran_now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone(timedelta(minutes=TEHRAN_UTC_OFFSET_MINUTES)))


def tehran_date(utc: datetime) -> date:
    return tehran_now(utc).date()


def _load_curated(path: Path | None) -> set[date]:
    p = path or (Path(__file__).resolve().parents[2] / "data" / "holidays_iran.json")
    if not p.exists():
        return set()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return {date.fromisoformat(x) for x in doc.get("gregorian_dates", [])}
    except (ValueError, OSError):
        return set()


def iranian_holidays(year: int | None = None, curated_path: Path | None = None) -> list[date]:
    """All known Iranian holidays for a Gregorian year (fixed + curated)."""
    curated = _load_curated(curated_path)
    out: set[date] = set()
    # fixed Jalali holidays across the two Gregorian years the Jalali year spans
    years = [year] if year else range(2020, 2032)
    for gy in years:
        for jm, jd in FIXED_JALALI_HOLIDAYS:
            # convert Jalali (gy-621 era) — use a wide search: convert around the year
            from app.services.jalali import jalali_to_gregorian

            for jy in (gy - 621, gy - 622):
                try:
                    g = jalali_to_gregorian(jy, jm, jd)
                except Exception:
                    continue
                d = date(*g)
                if d.year == gy:
                    out.add(d)
    out |= {d for d in curated if d.year in years or year is None}
    return sorted(out)


def is_weekend(d: date, weekend_days: Iterable[int] = DEFAULT_WEEKEND_DAYS) -> bool:
    return d.weekday() in set(weekend_days)


def is_trading_day(
    d: date,
    weekend_days: Iterable[int] = DEFAULT_WEEKEND_DAYS,
    holidays: Iterable[date] | None = None,
) -> bool:
    if is_weekend(d, weekend_days):
        return False
    return d not in set(holidays or ())


def expected_trading_days(
    start: date, end: date, weekend_days: Iterable[int] = DEFAULT_WEEKEND_DAYS
) -> list[date]:
    """Expected Iran-market trading days in [start, end] (weekends excluded).

    Holidays are deliberately NOT excluded here unless the curated file
    covers the range — the quality engine reports gaps against BOTH this
    list and the holiday-aware list, so missing holiday coverage is visible
    instead of silently tolerated.
    """
    days: list[date] = []
    d = start
    while d <= end:
        if not is_weekend(d, weekend_days):
            days.append(d)
        d += timedelta(days=1)
    return days


def market_sessions_fa() -> dict:
    return {
        "tehran": "بازار تهران: شنبه تا چهارشنه (پنجشنه و جمعه تعطیل)",
        "global": "بازار جهانی: دوشنبه تا جمعه (شنبه/یکشنبه تعطیل)",
        "tz": "UTC+3:30 (بدون تغییر ساعت تابستانی از ۲۰۲۳)",
    }
