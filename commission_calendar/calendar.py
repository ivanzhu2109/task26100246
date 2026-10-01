"""Subscription-month boundary arithmetic.

A subscription month is anchored on the day-of-month of the original
service start date. Boundary k is computed independently from the anchor:
month(start) + k months, day clamped to the last day of that month.
Clamping never propagates: a Jan-31 start yields Feb-28 then Mar-31.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date


def last_day_of_month(year: int, month: int) -> int:
    return _cal.monthrange(year, month)[1]


def add_months_clamped(start: date, months: int) -> date:
    """Boundary `months` subscription-months after `start`."""
    if months < 0:
        raise ValueError("months must be >= 0")
    total = (start.year * 12 + (start.month - 1)) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(start.day, last_day_of_month(year, month))
    return date(year, month, day)


def subscription_month_bounds(start: date, index: int) -> tuple[date, date]:
    """[begin, end) of the index-th subscription month (0-based)."""
    return add_months_clamped(start, index), add_months_clamped(start, index + 1)


def month_index_containing(start: date, day: date) -> int:
    """Index of the subscription month containing `day` (day >= start)."""
    if day < start:
        raise ValueError("day before service start")
    # Candidate by raw month distance, then fix up for clamping.
    raw = (day.year - start.year) * 12 + (day.month - start.month)
    while add_months_clamped(start, raw) > day:
        raw -= 1
    while add_months_clamped(start, raw + 1) <= day:
        raw += 1
    return raw
