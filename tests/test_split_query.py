"""Splitting a range into consecutive queries must match one whole query,
even for tiny amounts accumulating over years and mid-history starts."""
from __future__ import annotations

from datetime import date

from commission_calendar import CommissionCalendar, PriceRecord, Subscription
from tests.reference import reference_query


def tiny_sub() -> Subscription:
    # 1 cent/month at 10%: daily accrual is a tiny fraction of a cent.
    return Subscription(
        txn_id="TINY",
        partner_id="P1",
        deal_date=date(2019, 1, 31),
        window_months=None,
        prices=(PriceRecord(date(2019, 1, 31), 1),),
    )


def build_cal() -> CommissionCalendar:
    return CommissionCalendar([tiny_sub()])


def test_tiny_amount_long_accumulation_matches_reference():
    cal = build_cal()
    got = cal.query(date(2019, 1, 1), date(2025, 1, 1))
    assert got == reference_query([tiny_sub()], date(2019, 1, 1), date(2025, 1, 1))
    # 6 years at ~0.1 cent/month: only rounding of the cumulative matters.
    assert sum(got["TINY"]) <= 8


def test_mid_history_start_uses_origin_rounding():
    cal = build_cal()
    whole = cal.query(date(2019, 1, 1), date(2025, 1, 1))["TINY"]
    mid = cal.query(date(2022, 6, 1), date(2025, 1, 1))["TINY"]
    # The mid-history query must equal the tail of the whole-history query.
    assert mid == whole[41:]  # Jan 2019 .. May 2022 = 41 months


def test_split_queries_concatenate_to_whole():
    cal = build_cal()
    whole = cal.query(date(2019, 1, 1), date(2025, 1, 1))["TINY"]
    splits = (
        cal.query(date(2019, 1, 1), date(2020, 7, 1))["TINY"]
        + cal.query(date(2020, 7, 1), date(2022, 3, 1))["TINY"]
        + cal.query(date(2022, 3, 1), date(2023, 12, 1))["TINY"]
        + cal.query(date(2023, 12, 1), date(2025, 1, 1))["TINY"]
    )
    assert splits == whole


def test_month_by_month_queries_concatenate_to_whole():
    cal = build_cal()
    whole = cal.query(date(2020, 2, 1), date(2022, 2, 1))["TINY"]
    piecewise: list[int] = []
    y, m = 2020, 2
    while (y, m) < (2022, 2):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        piecewise += cal.query(date(y, m, 1), date(ny, nm, 1))["TINY"]
        y, m = ny, nm
    assert piecewise == whole


def test_months_outside_eligibility_are_zero():
    sub = Subscription(
        txn_id="W",
        partner_id="P1",
        deal_date=date(2024, 3, 10),
        window_months=6,
        prices=(PriceRecord(date(2024, 3, 10), 5000),),
        cancel_date=None,
    )
    cal = CommissionCalendar([sub])
    got = cal.query(date(2024, 1, 1), date(2025, 3, 1))["W"]
    assert got[0] == 0 and got[1] == 0  # before service start
    assert got[2] != 0  # March: service begins
    # Window ends on the 6th boundary: 2024-09-10. October onwards is zero.
    assert got[8] != 0  # September: partial eligibility through the 9th
    assert got[9:] == [0] * 5
