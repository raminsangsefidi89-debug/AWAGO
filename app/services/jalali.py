"""Jalali (Persian/Solar-Hijri) date conversion — small, tested, dependency-free.

Algorithm: the classic 33-year-cycle conversion (same family as the widely
used Borkowski/jdatetime implementations). The JavaScript port in
``app/static/js/core/jalali.js`` mirrors this module 1:1; this Python version
is the tested reference (used for print reports) and the test-suite pins it
against well-known anchor dates and round-trips.
"""

from __future__ import annotations

from datetime import date

_GREGORIAN_MONTH_DAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]

MONTHS_FA = [
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + _GREGORIAN_MONTH_DAYS[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = (
        365 * jy
        + (jy // 33) * 8
        + (jy % 33 + 3) // 4
        + 78
        + jd
        + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186)
    )
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    months = [0, 31, 29 if _is_leap_gregorian(gy) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > months[gm]:
        gd -= months[gm]
        gm += 1
    return gy, gm, gd


def _is_leap_gregorian(gy: int) -> bool:
    return (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0


def to_jalali(d: date) -> tuple[int, int, int]:
    return gregorian_to_jalali(d.year, d.month, d.day)


def format_jalali_fa(d: date) -> str:
    """'۱۴۰۵/۰۹/۰۵' with Persian digits."""
    jy, jm, jd = to_jalali(d)
    return digits_fa(f"{jy:04d}/{jm:02d}/{jd:02d}")


def format_jalali_long_fa(d: date) -> str:
    """'۵ آذر ۱۴۰۵' with Persian month names."""
    jy, jm, jd = to_jalali(d)
    return digits_fa(f"{jd} {MONTHS_FA[jm - 1]} {jy}")


def digits_fa(text: str) -> str:
    trans = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return text.translate(trans)
