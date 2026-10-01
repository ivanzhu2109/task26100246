"""Small-sample amounts must match the independent daily reference."""
from __future__ import annotations

import random
from datetime import date, timedelta

from commission_calendar import CommissionCalendar, PriceRecord, Subscription
from commission_calendar.calendar import add_months_clamped
from tests.reference import reference_query


def make(**kw) -> Subscription:
    defaults = dict(
        txn_id="T1",
        partner_id="P1",
        deal_date=date(2023, 1, 31),
        window_months=None,
        prices=(PriceRecord(date(2023, 1, 31), 1000),),
        cancel_date=None,
    )
    defaults.update(kw)
    return Subscription(**defaults)


def test_month_end_start_boundaries_across_leap_years():
    start = date(2023, 1, 31)
    assert add_months_clamped(start, 1) == date(2023, 2, 28)  # non-leap
    assert add_months_clamped(start, 2) == date(2023, 3, 31)  # anchor restored
    assert add_months_clamped(start, 13) == date(2024, 2, 29)  # leap
    assert add_months_clamped(start, 14) == date(2024, 3, 31)
    assert add_months_clamped(start, 25) == date(2025, 2, 28)


def test_month_end_start_matches_reference_over_leap_cycle():
    sub = make()
    cal = CommissionCalendar([sub])
    got = cal.query(date(2023, 1, 1), date(2026, 1, 1))
    want = reference_query([sub], date(2023, 1, 1), date(2026, 1, 1))
    assert got == want


def test_price_change_on_anchor_day():
    sub = make(
        prices=(
            PriceRecord(date(2023, 1, 31), 1000),
            PriceRecord(date(2023, 3, 31), 2500),  # exactly a boundary
            PriceRecord(date(2023, 4, 15), 700),   # mid-month
        )
    )
    cal = CommissionCalendar([sub])
    got = cal.query(date(2023, 1, 1), date(2023, 7, 1))
    assert got == reference_query([sub], date(2023, 1, 1), date(2023, 7, 1))


def test_price_change_on_termination_day():
    # Cancel on 2023-04-15: that day earns 0; price change same day is moot.
    sub = make(
        prices=(
            PriceRecord(date(2023, 1, 31), 1000),
            PriceRecord(date(2023, 4, 15), 9999),
        ),
        cancel_date=date(2023, 4, 15),
    )
    cal = CommissionCalendar([sub])
    got = cal.query(date(2023, 1, 1), date(2023, 8, 1))
    assert got == reference_query([sub], date(2023, 1, 1), date(2023, 8, 1))
    assert got["T1"][3] != 0  # April 1..14 still eligible
    assert got["T1"][4:] == [0, 0, 0]  # May onwards: nothing


def test_window_end_and_cancel_take_earlier():
    # 6-month window ends 2023-07-31; cancel 2023-05-20 is earlier.
    sub = make(window_months=6, cancel_date=date(2023, 5, 20))
    cal = CommissionCalendar([sub])
    got = cal.query(date(2023, 1, 1), date(2024, 1, 1))
    assert got == reference_query([sub], date(2023, 1, 1), date(2024, 1, 1))
    assert got["T1"][4] != 0 and got["T1"][5] == 0  # May partial, June zero


def test_window_end_boundary_day_earns_nothing():
    sub = make(window_months=6)
    cal = CommissionCalendar([sub])
    got = cal.query(date(2023, 7, 1), date(2023, 9, 1))
    # Window ends on the 6th boundary 2023-07-31; July has 30 eligible days.
    assert got == reference_query([sub], date(2023, 7, 1), date(2023, 9, 1))
    assert got["T1"][1] == 0  # August: nothing


def test_randomized_small_samples_match_reference():
    rng = random.Random(20261002)
    for trial in range(30):
        start = date(2020, 1, 1) + timedelta(days=rng.randrange(0, 365 * 3))
        n_prices = rng.randrange(1, 6)
        price_dates = {start}
        while len(price_dates) < n_prices:
            price_dates.add(start + timedelta(days=rng.randrange(0, 800)))
        prices = tuple(
            PriceRecord(d, rng.randrange(0, 5000)) for d in sorted(price_dates)
        )
        window = rng.choice([None, 6, 12, 24])
        cancel = (
            start + timedelta(days=rng.randrange(0, 900))
            if rng.random() < 0.5
            else None
        )
        sub = Subscription(
            txn_id=f"T{trial}",
            partner_id="P1",
            deal_date=start,
            window_months=window,
            prices=prices,
            cancel_date=cancel,
        )
        qstart = date(2020, 1, 1) + timedelta(days=rng.randrange(0, 365))
        qstart = qstart.replace(day=1)
        qend_months = rng.randrange(24, 48)
        y, m = divmod(qstart.year * 12 + qstart.month - 1 + qend_months, 12)
        qend = date(y, m + 1, 1)
        cal = CommissionCalendar([sub])
        assert cal.query(qstart, qend) == reference_query([sub], qstart, qend), (
            f"trial {trial}: {sub}"
        )
