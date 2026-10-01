"""Subscription-month boundary arithmetic.

Boundaries are anchored on the original start day-of-month: each boundary
takes the original day-of-month, clamped to the last day of the target
month. Clamping never propagates to later boundaries.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date


def add_months_clamped(start: date, months: int) -> date:
    """Date ``months`` subscription-months after ``start``, clamped by anchor day."""
    total = (start.year * 12 + start.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day)


def boundary_index(anchor: date, day: date) -> int:
    """Index k such that boundary_k <= day < boundary_{k+1} (day >= anchor)."""
    if day < anchor:
        raise ValueError("day before anchor")
    k = (day.year - anchor.year) * 12 + (day.month - anchor.month)
    # Clamping can shift a boundary by a few days; adjust by at most 1.
    if add_months_clamped(anchor, k) > day:
        k -= 1
    elif add_months_clamped(anchor, k + 1) <= day:
        k += 1
    return k
