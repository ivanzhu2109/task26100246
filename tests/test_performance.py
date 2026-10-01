"""Reproducible scale test: 10k subscriptions, 30 years, <=20 price changes.

From snapshot hand-off to full results for the final 12 calendar months
must complete in under 10 seconds (including first-computation cost).
"""
from __future__ import annotations

import random
import time
from datetime import date, timedelta

import pytest

from commission_calendar import CommissionCalendar, PriceRecord, Subscription

N_SUBS = 10_000
MAX_PRICES = 20
HISTORY_YEARS = 30
TIME_BUDGET_S = 10.0

START = date(1995, 1, 1)
END = date(1995 + HISTORY_YEARS, 1, 1)
TOTAL_DAYS = (END - START).days


def build_snapshot() -> list[Subscription]:
    rng = random.Random(26100246)  # fixed seed: reproducible
    subs: list[Subscription] = []
    for i in range(N_SUBS):
        deal = START + timedelta(days=rng.randrange(TOTAL_DAYS - 400))
        n_prices = rng.randrange(1, MAX_PRICES + 1)
        offsets = sorted(rng.sample(range(1, 400), n_prices - 1))
        prices = [PriceRecord(deal, rng.randrange(0, 100_000))]
        for off in offsets:
            prices.append(PriceRecord(deal + timedelta(days=off), rng.randrange(0, 100_000)))
        subs.append(
            Subscription(
                txn_id=f"TXN{i:05d}",
                partner_id=f"PARTNER{i % 250}",
                deal_date=deal,
                window_months=rng.choice([None, 6, 12, 24]),
                prices=tuple(prices),
                cancel_date=(
                    deal + timedelta(days=rng.randrange(1, 800))
                    if rng.random() < 0.3
                    else None
                ),
            )
        )
    return subs


@pytest.fixture(scope="module")
def snapshot() -> list[Subscription]:
    return build_snapshot()


def test_scale_query_under_budget(snapshot: list[Subscription]) -> None:
    t0 = time.perf_counter()
    cal = CommissionCalendar(snapshot)
    result = cal.query(date(2024, 1, 1), date(2025, 1, 1))
    elapsed = time.perf_counter() - t0
    assert len(result) == N_SUBS
    assert all(len(v) == 12 for v in result.values())
    assert all(all(isinstance(c, int) and c >= 0 for c in v) for v in result.values())
    assert elapsed < TIME_BUDGET_S, f"took {elapsed:.2f}s"
    print(f"\n10k subs / 30y history / 12-month query: {elapsed:.2f}s")


def test_repeated_queries_are_cheap(snapshot: list[Subscription]) -> None:
    cal = CommissionCalendar(snapshot)
    cal.query(date(2024, 1, 1), date(2025, 1, 1))
    t0 = time.perf_counter()
    again = cal.query(date(2024, 1, 1), date(2025, 1, 1))
    elapsed = time.perf_counter() - t0
    assert again == cal.query(date(2024, 1, 1), date(2025, 1, 1))
    assert elapsed < TIME_BUDGET_S
    print(f"\nrepeat 12-month query: {elapsed:.2f}s")
