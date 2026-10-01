"""Independent brute-force reference: exact day-by-day accrual.

Deliberately shares no code with the library under test. Used to validate
small-sample amounts against an obvious, slow, exact implementation.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from fractions import Fraction

from commission_calendar.models import Subscription

_ONE_DAY = timedelta(days=1)


def _add_months(d: date, months: int) -> date:
    total = (d.year * 12 + d.month - 1) + months
    year, month = divmod(total, 12)
    return date(year, month + 1, min(d.day, monthrange(year, month + 1)[1]))


def _rate_map(subs: list[Subscription]) -> dict[str, int]:
    rates: dict[str, int] = {}
    partners: dict[str, list[Subscription]] = {}
    for s in subs:
        partners.setdefault(s.partner_id, []).append(s)
    for group in partners.values():
        group.sort(key=lambda s: (s.deal_date, s.txn_id))
        for i, s in enumerate(group):
            rates[s.txn_id] = 10 if i < 10 else 15
    return rates


def _price_on(sub: Subscription, day: date) -> int:
    mrr = 0
    for rec in sub.prices:
        if rec.effective_date <= day:
            mrr = rec.mrr_cents
    return mrr


def _month_dim(anchor: date, day: date) -> int:
    """Length of the subscription month containing ``day``."""
    k = (day.year - anchor.year) * 12 + (day.month - anchor.month)
    while _add_months(anchor, k) > day:
        k -= 1
    while _add_months(anchor, k + 1) <= day:
        k += 1
    return (_add_months(anchor, k + 1) - _add_months(anchor, k)).days


def _termination(sub: Subscription) -> date | None:
    ends = []
    if sub.window_months is not None:
        ends.append(_add_months(sub.deal_date, sub.window_months))
    if sub.cancel_date is not None:
        ends.append(sub.cancel_date)
    return min(ends) if ends else None


def _round_half_up(frac: Fraction) -> int:
    return (frac.numerator * 2 + frac.denominator) // (2 * frac.denominator)


def reference_query(
    subs: list[Subscription], start_month: date, end_month: date
) -> dict[str, list[int]]:
    """Monthly cents per subscription via exact daily accrual."""
    rates = _rate_map(subs)
    months: list[date] = []
    m = start_month
    while m < end_month:
        months.append(m)
        total = m.year * 12 + m.month
        m = date(total // 12, total % 12 + 1, 1)
    last_day = date(
        months[-1].year, months[-1].month, monthrange(months[-1].year, months[-1].month)[1]
    )
    result: dict[str, list[int]] = {}
    for sub in subs:
        term = _termination(sub)
        cum = Fraction(0)
        cum_by_day: dict[date, Fraction] = {}
        day = sub.deal_date
        while day <= last_day:
            if term is None or day < term:
                mrr = _price_on(sub, day)
                if mrr:
                    cum += Fraction(mrr * rates[sub.txn_id], 100 * _month_dim(sub.deal_date, day))
            cum_by_day[day] = cum
            day += _ONE_DAY
        amounts: list[int] = []
        prev = _round_half_up(
            cum_by_day.get(start_month - _ONE_DAY, Fraction(0))
        )
        for mstart in months:
            mend = date(mstart.year, mstart.month, monthrange(mstart.year, mstart.month)[1])
            rounded = _round_half_up(cum_by_day.get(mend, Fraction(0)))
            amounts.append(rounded - prev)
            prev = rounded
        result[sub.txn_id] = amounts
    return result
