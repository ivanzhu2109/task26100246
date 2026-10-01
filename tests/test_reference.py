"""Cross-check the engine against the brute-force day-by-day reference."""

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reference import reference_monthly

from commission_calendar import (
    CommissionCalendar,
    PriceRecord,
    Snapshot,
    Subscription,
    Window,
)

ONE_DAY = timedelta(days=1)


def _engine_monthly(snapshot, start_month, end_month):
    return CommissionCalendar(snapshot).query(start_month, end_month).amounts


def test_month_end_start_across_leap_year_with_price_change_and_cancel():
    # Start Jan 31 2023, crosses non-leap 2023 and leap 2024 February.
    # Price changes exactly on a subscription-month anchor (2024-02-29),
    # cancellation lands mid subscription month.
    sub = Subscription(
        "T1",
        "P1",
        date(2023, 1, 31),
        Window.LIFETIME,
        (
            PriceRecord(date(2023, 1, 31), 10000),
            PriceRecord(date(2023, 6, 15), 25000),
            PriceRecord(date(2024, 2, 29), 7777),  # exactly on clamped anchor
        ),
        cancel_date=date(2024, 5, 17),
    )
    snap = Snapshot((sub,))
    got = _engine_monthly(snap, date(2023, 1, 1), date(2024, 8, 1))
    want = reference_monthly(snap, date(2023, 1, 1), date(2024, 8, 1))
    assert got == want
    # Cancel 2024-05-17: May (index 16) still accrues May 1-16, then 0.
    assert got["T1"][16] > 0
    assert all(v == 0 for v in got["T1"][17:])


def test_price_change_on_anchor_and_window_expiry_same_day():
    # Window ends exactly on the 6th boundary; a price change lands the
    # same day and must never take effect.
    sub = Subscription(
        "T2",
        "P1",
        date(2024, 1, 31),
        Window.MONTHS_6,
        (
            PriceRecord(date(2024, 1, 31), 9000),
            PriceRecord(date(2024, 7, 31), 99000),  # == window end boundary
        ),
    )
    snap = Snapshot((sub,))
    got = _engine_monthly(snap, date(2024, 1, 1), date(2024, 10, 1))
    want = reference_monthly(snap, date(2024, 1, 1), date(2024, 10, 1))
    assert got == want
    # Window end is 2024-07-31: July accrues Jul 1-30 at the OLD price only.
    assert got["T2"][6] > 0
    assert all(v == 0 for v in got["T2"][7:])


def test_cancel_before_window_end_wins():
    sub = Subscription(
        "T3",
        "P1",
        date(2023, 3, 10),
        Window.MONTHS_12,
        (PriceRecord(date(2023, 3, 10), 5000),),
        cancel_date=date(2023, 8, 1),
    )
    snap = Snapshot((sub,))
    got = _engine_monthly(snap, date(2023, 3, 1), date(2024, 5, 1))
    want = reference_monthly(snap, date(2023, 3, 1), date(2024, 5, 1))
    assert got == want
    assert got["T3"][5] == 0  # 2023-08: cancel day itself yields nothing
    assert all(v == 0 for v in got["T3"][5:])


def test_randomized_small_samples_match_reference():
    rng = random.Random(20261002)
    for trial in range(30):
        n_subs = rng.randint(1, 4)
        subs = []
        for i in range(n_subs):
            start = date(2023, 1, 1) + timedelta(days=rng.randint(0, 500))
            records = [PriceRecord(start, rng.choice([0, 1, 7, 999, 12345]))]
            for _ in range(rng.randint(0, 3)):
                eff = start + timedelta(days=rng.randint(1, 400))
                if all(r.effective_date != eff for r in records):
                    records.append(PriceRecord(eff, rng.choice([0, 1, 7, 999, 54321])))
            window = rng.choice(list(Window))
            cancel = None
            if rng.random() < 0.4:
                cancel = start + timedelta(days=rng.randint(0, 400))
            subs.append(
                Subscription(f"T{i:02d}", f"P{rng.randint(1, 2)}", start, window,
                             tuple(records), cancel)
            )
        snap = Snapshot(tuple(subs))
        got = _engine_monthly(snap, date(2023, 1, 1), date(2025, 3, 1))
        want = reference_monthly(snap, date(2023, 1, 1), date(2025, 3, 1))
        assert got == want, f"trial {trial}"
