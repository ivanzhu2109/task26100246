"""Reproducible performance test: 10k subscriptions, <=20 price changes each,
30-year history, query the last 12 calendar months in under 10 seconds
including snapshot ingestion and first-time computation."""

import random
import time
from datetime import date, timedelta

from commission_calendar import (
    CommissionCalendar,
    PriceRecord,
    Snapshot,
    Subscription,
    Window,
)

N_SUBS = 10_000
MAX_PRICE_CHANGES = 20
HISTORY_YEARS = 30
TIME_BUDGET_SECONDS = 10.0


def _build_snapshot() -> Snapshot:
    rng = random.Random(26100246)  # fixed seed: fully reproducible
    start = date(1995, 1, 1)
    # Deals spread over the first 20 years; price changes within 10 years
    # after the deal, so the tail of the 30-year history is fully priced.
    deal_span = (date(2015, 1, 1) - start).days
    change_span = (date(2005, 1, 1) - date(1995, 1, 1)).days
    subs = []
    for i in range(N_SUBS):
        deal = start + timedelta(days=rng.randrange(deal_span))
        n_changes = rng.randint(1, MAX_PRICE_CHANGES)
        eff_dates = {deal}
        while len(eff_dates) < n_changes:
            eff_dates.add(deal + timedelta(days=rng.randrange(1, change_span)))
        records = tuple(
            PriceRecord(d, rng.randint(0, 2_000_00)) for d in sorted(eff_dates)
        )
        window = rng.choice((Window.MONTHS_6, Window.MONTHS_12,
                             Window.MONTHS_24, Window.LIFETIME))
        cancel = None
        if rng.random() < 0.3:
            cancel = deal + timedelta(days=rng.randrange(0, 365 * 5))
        subs.append(Subscription(
            f"T{i:05d}", f"P{rng.randint(1, 50)}", deal, window, records, cancel))
    return Snapshot(tuple(subs))


def test_performance_last_12_months():
    snapshot = _build_snapshot()
    t0 = time.perf_counter()
    cal = CommissionCalendar(snapshot)
    result = cal.query(date(2024, 1, 1), date(2025, 1, 1))
    elapsed = time.perf_counter() - t0

    assert len(result.months) == 12
    assert len(result.amounts) == N_SUBS
    assert all(len(v) == 12 for v in result.amounts.values())
    assert elapsed < TIME_BUDGET_SECONDS, f"took {elapsed:.2f}s"
    print(f"\nperf: {elapsed:.2f}s for {N_SUBS} subs x 12 months")
