from datetime import date

import pytest

from commission_calendar.calendar import (
    add_months_clamped,
    month_index_containing,
    subscription_month_bounds,
)


def test_anchor_day_preserved_after_short_month():
    start = date(2023, 1, 31)
    bounds = [add_months_clamped(start, k) for k in range(5)]
    assert bounds == [
        date(2023, 1, 31),
        date(2023, 2, 28),  # clamped, non-leap
        date(2023, 3, 31),  # original anchor restored
        date(2023, 4, 30),
        date(2023, 5, 31),
    ]


def test_leap_year_february():
    start = date(2024, 1, 31)
    assert add_months_clamped(start, 1) == date(2024, 2, 29)
    assert add_months_clamped(start, 2) == date(2024, 3, 31)
    start = date(2023, 1, 31)
    assert add_months_clamped(start, 13) == date(2024, 2, 29)


def test_year_rollover():
    assert add_months_clamped(date(2023, 11, 30), 2) == date(2024, 1, 30)
    assert add_months_clamped(date(2023, 12, 31), 1) == date(2024, 1, 31)
    assert add_months_clamped(date(2024, 2, 29), 12) == date(2025, 2, 28)


def test_mid_month_anchor_never_clamps():
    start = date(2024, 3, 15)
    for k in range(48):
        assert add_months_clamped(start, k).day == 15


def test_subscription_month_bounds_half_open():
    begin, end = subscription_month_bounds(date(2023, 1, 31), 1)
    assert begin == date(2023, 2, 28)
    assert end == date(2023, 3, 31)
    assert (end - begin).days == 31


def test_month_index_containing():
    start = date(2023, 1, 31)
    assert month_index_containing(start, date(2023, 1, 31)) == 0
    assert month_index_containing(start, date(2023, 2, 27)) == 0
    assert month_index_containing(start, date(2023, 2, 28)) == 1
    assert month_index_containing(start, date(2023, 3, 30)) == 1
    assert month_index_containing(start, date(2023, 3, 31)) == 2
    with pytest.raises(ValueError):
        month_index_containing(start, date(2023, 1, 30))
