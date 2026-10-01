"""Directed engine behavior tests."""

from datetime import date

import pytest

from commission_calendar import (
    CommissionCalendar,
    PriceRecord,
    Snapshot,
    Subscription,
    Window,
)


def _sub(txn, partner, deal, mrc, window=Window.LIFETIME, cancel=None):
    return Subscription(txn, partner, deal, window,
                        (PriceRecord(deal, mrc),), cancel)


def test_tier_boundary_same_day_deals_with_prior_cancellation():
    # 11 deals for one partner, all on the same day. ASCII txn order decides
    # the ranks; deal #4 is cancelled immediately but keeps its slot, so the
    # 11th deal (rank 10) is still the first at 15%.
    deal_day = date(2024, 2, 1)
    subs = []
    for i in range(11):
        txn = f"T{i:02d}"
        cancel = deal_day if txn == "T03" else None  # cancelled on day one
        subs.append(_sub(txn, "P1", deal_day, 10000, cancel=cancel))
    cal = CommissionCalendar(Snapshot(tuple(subs)))
    res = cal.query(date(2024, 2, 1), date(2024, 3, 1))
    # February 2024 has 29 days; subscription months are Feb 1 - Mar 1.
    # Full month accrual: 10% of 10000 = 1000; 15% = 1500.
    assert res.amounts["T00"][0] == 1000
    assert res.amounts["T03"][0] == 0  # cancelled at 00:00 on deal day
    assert res.amounts["T09"][0] == 1000  # rank 9, still 10%
    assert res.amounts["T10"][0] == 1500  # rank 10, first at 15%


def test_tiers_are_per_partner():
    subs = [_sub(f"A{i:02d}", "PA", date(2024, 1, 1), 10000) for i in range(11)]
    subs += [_sub(f"B{i:02d}", "PB", date(2024, 1, 1), 10000) for i in range(11)]
    cal = CommissionCalendar(Snapshot(tuple(subs)))
    res = cal.query(date(2024, 1, 1), date(2024, 2, 1))
    assert res.amounts["A10"][0] == 1500
    assert res.amounts["B10"][0] == 1500  # PB gets its own first-10 tier
    assert res.amounts["B09"][0] == 1000


def test_input_order_does_not_matter():
    subs = [_sub(f"T{i:02d}", "P1", date(2024, 1, 1), 100 * (i + 1)) for i in range(12)]
    forward = CommissionCalendar(Snapshot(tuple(subs))).query(
        date(2024, 1, 1), date(2024, 4, 1)).amounts
    reversed_input = CommissionCalendar(Snapshot(tuple(reversed(subs)))).query(
        date(2024, 1, 1), date(2024, 4, 1)).amounts
    assert forward == reversed_input


def test_half_cent_rounds_up_on_cumulative():
    # mrc 1 cent at 10% over a 2-day subscription month would be 0.05/day;
    # use a case hitting exactly x.5 cumulative: mrc=5, 10%, 31-day month,
    # one day elapsed => 5*0.1/31 not exact. Instead craft exact half:
    # mrc=10, rate 10%, month of 28 days, 14 days elapsed => 14*10*0.1/28 = 0.5
    sub = Subscription(
        "T1", "P1", date(2023, 2, 1), Window.LIFETIME,
        (PriceRecord(date(2023, 2, 1), 10),), cancel_date=date(2023, 2, 15),
    )
    cal = CommissionCalendar(Snapshot((sub,)))
    res = cal.query(date(2023, 2, 1), date(2023, 4, 1))
    # Cumulative at Mar 1 is exactly 0.5 cents -> rounds up to 1.
    assert res.amounts["T1"] == [1, 0]


def test_tiny_amounts_accumulate_and_split_queries_match_whole():
    # 1 cent MRC at 10%: ~0.0032 cents/day. Over 30 years it must still
    # accumulate exactly, and splitting the query must not change results.
    sub = _sub("TINY", "P1", date(2024, 1, 31), 1)
    cal = CommissionCalendar(Snapshot((sub,)))
    whole = cal.query(date(2024, 1, 1), date(2026, 1, 1)).amounts["TINY"]
    split_a = cal.query(date(2024, 1, 1), date(2024, 7, 1)).amounts["TINY"]
    split_b = cal.query(date(2024, 7, 1), date(2025, 2, 1)).amounts["TINY"]
    split_c = cal.query(date(2025, 2, 1), date(2026, 1, 1)).amounts["TINY"]
    assert whole == split_a + split_b + split_c
    # 24 months * ~0.1 cent/month accumulates to a few cents eventually.
    assert sum(whole) > 0
    # Mid-history start: cumulative rounding still anchored at service start.
    mid = cal.query(date(2025, 6, 1), date(2025, 9, 1)).amounts["TINY"]
    assert mid == whole[17:20]


def test_query_before_service_start_is_zero():
    sub = _sub("T1", "P1", date(2024, 6, 15), 10000)
    cal = CommissionCalendar(Snapshot((sub,)))
    res = cal.query(date(2024, 1, 1), date(2024, 7, 1))
    assert res.amounts["T1"][:5] == [0, 0, 0, 0, 0]
    assert res.amounts["T1"][5] > 0  # June: half a subscription month


def test_window_6_12_24_end_boundaries():
    for window, n in ((Window.MONTHS_6, 6), (Window.MONTHS_12, 12), (Window.MONTHS_24, 24)):
        sub = _sub("T1", "P1", date(2023, 1, 31), 3100, window=window)
        cal = CommissionCalendar(Snapshot((sub,)))
        res = cal.query(date(2023, 1, 1), date(2026, 1, 1))
        amounts = res.amounts["T1"]
        # Last accruing subscription month starts at boundary n-1.
        # Window end boundary is add_months_clamped(start, n); after the
        # calendar month containing it, everything is 0.
        assert sum(amounts) > 0
        # Total exact accrual: n full subscription months at 10% of 3100.
        assert sum(amounts) in (n * 310 - 1, n * 310, n * 310 + 1)


def test_validation_errors():
    good = _sub("T1", "P1", date(2024, 1, 1), 100)
    with pytest.raises(ValueError):
        CommissionCalendar(Snapshot((good, good)))  # duplicate txn
    with pytest.raises(ValueError):
        CommissionCalendar(Snapshot((_sub("Té", "P1", date(2024, 1, 1), 100),)))
    with pytest.raises(ValueError):
        CommissionCalendar(Snapshot((Subscription(
            "T2", "P1", date(2024, 1, 1), Window.LIFETIME, ()),)))
    with pytest.raises(ValueError):
        CommissionCalendar(Snapshot((Subscription(
            "T3", "P1", date(2024, 1, 1), Window.LIFETIME,
            (PriceRecord(date(2024, 1, 2), 100),)),)))  # not starting at deal date
    with pytest.raises(ValueError):
        CommissionCalendar(Snapshot((_sub("T4", "P1", date(2024, 1, 1), -5),)))
    cal = CommissionCalendar(Snapshot((good,)))
    with pytest.raises(ValueError):
        cal.query(date(2024, 1, 15), date(2024, 2, 1))  # not month start
    with pytest.raises(ValueError):
        cal.query(date(2024, 3, 1), date(2024, 2, 1))  # empty range
