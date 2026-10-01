"""Independent brute-force reference: exact day-by-day accrual.

Deliberately shares no code with the engine. Used to cross-check the
engine on small samples.
"""

from __future__ import annotations

from datetime import date, timedelta
from fractions import Fraction

from commission_calendar.calendar import add_months_clamped, month_index_containing
from commission_calendar.models import Snapshot, Subscription, Window

ONE_DAY = timedelta(days=1)


def _tier_rates(snapshot: Snapshot) -> dict[str, Fraction]:
    by_partner: dict[str, list[Subscription]] = {}
    for sub in snapshot.subscriptions:
        by_partner.setdefault(sub.partner_id, []).append(sub)
    rates: dict[str, Fraction] = {}
    for subs in by_partner.values():
        subs.sort(key=lambda s: (s.deal_date, s.txn_id))
        for rank, sub in enumerate(subs):
            rates[sub.txn_id] = Fraction(10 if rank < 10 else 15, 100)
    return rates


def _termination(sub: Subscription) -> date | None:
    end = None
    if sub.window is not Window.LIFETIME:
        end = add_months_clamped(sub.deal_date, sub.window.value)
    if sub.cancel_date is not None and (end is None or sub.cancel_date < end):
        end = sub.cancel_date
    return end


def _mrc_on(sub: Subscription, day: date) -> int:
    # latest record with effective_date <= day
    best = None
    for rec in sub.price_records:
        if rec.effective_date <= day and (best is None or rec.effective_date > best):
            best = rec.effective_date
    if best is None:
        return 0
    for rec in sub.price_records:
        if rec.effective_date == best:
            return rec.mrc_cents
    return 0


def reference_monthly(snapshot: Snapshot, start_month: date, end_month: date) -> dict[str, list[int]]:
    """{txn_id: [rounded monthly amounts]} computed one day at a time."""
    rates = _tier_rates(snapshot)
    months: list[date] = []
    cur = start_month
    while cur < end_month:
        months.append(cur)
        cur = add_months_clamped(cur, 1)

    result: dict[str, list[int]] = {}
    for sub in snapshot.subscriptions:
        rate = rates[sub.txn_id]
        term = _termination(sub)
        cum = Fraction(0)
        rounded_prev = 0
        amounts: list[int] = []
        day = sub.deal_date
        # Walk every day from service start to end_month, tracking the
        # subscription-month day count from the anchor rules directly.
        for month_start in months + [end_month]:
            while day < month_start:
                eligible = term is None or day < term
                if eligible and day >= sub.deal_date:
                    k = month_index_containing(sub.deal_date, day)
                    begin = add_months_clamped(sub.deal_date, k)
                    end = add_months_clamped(sub.deal_date, k + 1)
                    dim = (end - begin).days
                    cum += Fraction(_mrc_on(sub, day), dim) * rate
                day += ONE_DAY
            rounded = (2 * cum.numerator + cum.denominator) // (2 * cum.denominator)
            if month_start != start_month:
                amounts.append(rounded - rounded_prev)
            rounded_prev = rounded
        result[sub.txn_id] = amounts
    return result
