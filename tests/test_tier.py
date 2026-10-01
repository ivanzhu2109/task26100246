"""Tier ladder: per partner, deal-date asc, txn_id ASCII tie-break.

Cancelled subscriptions still occupy their rank. Input order is irrelevant.
"""
from __future__ import annotations

import random
from datetime import date

from commission_calendar import CommissionCalendar, PriceRecord, Subscription
from commission_calendar.api import _assign_rates


def sub(txn: str, partner: str = "P1", deal: date = date(2024, 1, 10), **kw) -> Subscription:
    return Subscription(
        txn_id=txn,
        partner_id=partner,
        deal_date=deal,
        window_months=kw.get("window_months"),
        prices=(PriceRecord(deal, 1000),),
        cancel_date=kw.get("cancel_date"),
    )


def test_same_day_tier_boundary_with_cancelled_predecessors():
    # 12 deals on the same day; txn ASCII order decides rank.
    # T00 and T05 are cancelled before the query window but keep their rank.
    subs = [
        sub("T00", cancel_date=date(2024, 2, 1)),
        sub("T01"),
        sub("T02"),
        sub("T03"),
        sub("T04"),
        sub("T05", cancel_date=date(2024, 2, 1)),
        sub("T06"),
        sub("T07"),
        sub("T08"),
        sub("T09"),
        sub("T10"),
        sub("T11"),
    ]
    rng = random.Random(7)
    rng.shuffle(subs)  # input order must not matter
    cal = CommissionCalendar(subs)
    rates = _assign_rates(subs)
    for i in range(10):
        assert rates[f"T{i:02d}"] == 10
    assert rates["T10"] == 15
    assert rates["T11"] == 15
    # Query after the cancellations: ranks still respected for the survivors.
    got = cal.query(date(2024, 3, 1), date(2024, 4, 1))
    assert got["T00"] == [0]  # cancelled, but its 10% slot is not reused
    # Natural months misalign with subscription months; check the ratio instead.
    assert got["T09"] == [102]  # 10% tier
    assert got["T10"] == [153]  # 15% tier
    assert got["T11"] == [153]


def test_ascii_lexicographic_not_numeric():
    # ASCII order: T1 < T10 < T11 < T2 < ... < T9; the 11th slot is 'T9'.
    txns = ["T1", "T10", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T11"]
    subs = [sub(t) for t in txns]
    rates = _assign_rates(subs)
    ordered = sorted(txns)  # ASCII order
    for rank, txn in enumerate(ordered):
        expect = 10 if rank < 10 else 15
        assert rates[txn] == expect, (txn, rates[txn])
    assert rates["T9"] == 15  # 11th in ASCII order
    assert rates["T11"] == 10  # 3rd in ASCII order


def test_tiers_are_per_partner():
    subs = [sub(f"A{i:02d}", partner="PA") for i in range(11)]
    subs += [sub(f"B{i:02d}", partner="PB") for i in range(11)]
    rates = _assign_rates(subs)
    assert rates["A09"] == 10 and rates["A10"] == 15
    assert rates["B09"] == 10 and rates["B10"] == 15


def test_deal_date_dominates_txn_order():
    subs = [
        sub("Z1", deal=date(2024, 1, 1)),
        sub("A1", deal=date(2024, 1, 2)),
    ]
    rates = _assign_rates(subs)
    assert rates["Z1"] == 10  # earlier deal date ranks first despite 'Z'
    assert rates["A1"] == 10  # both within first 10 anyway
    subs = [sub(f"X{i:02d}", deal=date(2024, 1, 2)) for i in range(10)]
    subs.append(sub("ZZ", deal=date(2024, 1, 1)))  # earliest deal, last name
    rates = _assign_rates(subs)
    assert rates["ZZ"] == 10
    assert rates["X09"] == 15  # pushed to 11th by the earlier deal
