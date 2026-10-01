"""Public query API."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Iterable

from .engine import SubscriptionLedger, round_half_up_cents
from .models import Subscription, validate_snapshot

TIER_SIZE = 10
TIER_RATES_PCT = (10, 15)  # first TIER_SIZE deals per partner, then the rest

_ONE_DAY = timedelta(days=1)


def _assign_rates(subscriptions: list[Subscription]) -> dict[str, int]:
    """Commission rate (percent) per txn_id from the partner-level tier ladder."""
    rates: dict[str, int] = {}
    by_partner: dict[str, list[Subscription]] = {}
    for sub in subscriptions:
        by_partner.setdefault(sub.partner_id, []).append(sub)
    for partner_subs in by_partner.values():
        partner_subs.sort(key=lambda s: (s.deal_date, s.txn_id))
        for rank, sub in enumerate(partner_subs):
            rates[sub.txn_id] = (
                TIER_RATES_PCT[0] if rank < TIER_SIZE else TIER_RATES_PCT[1]
            )
    return rates


def _month_end(month_start: date) -> date:
    return date(
        month_start.year,
        month_start.month,
        monthrange(month_start.year, month_start.month)[1],
    )


def _next_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


class CommissionCalendar:
    """In-memory commission calendar built from a full read-only snapshot."""

    def __init__(self, subscriptions: Iterable[Subscription]) -> None:
        subs = list(subscriptions)
        validate_snapshot(subs)
        rates = _assign_rates(subs)
        self._ledgers = {
            sub.txn_id: SubscriptionLedger(sub, rates[sub.txn_id]) for sub in subs
        }

    def query(self, start_month: date, end_month: date) -> dict[str, list[int]]:
        """Monthly commission cents per subscription for [start_month, end_month).

        Both bounds must be first-of-month dates; the start month is included,
        the end month is excluded. Returns ``txn_id -> [cents per month]``.
        Each monthly figure is the difference of two cumulative amounts that
        were each rounded half-up to cents only after exact accumulation from
        the original service start date.
        """
        if start_month.day != 1 or end_month.day != 1:
            raise ValueError("query bounds must be first-of-month dates")
        if not start_month < end_month:
            raise ValueError("start_month must be before end_month")
        month_ends: list[date] = []
        m = start_month
        while m < end_month:
            month_ends.append(_month_end(m))
            m = _next_month(m)
        result: dict[str, list[int]] = {}
        for txn_id, ledger in self._ledgers.items():
            prev_rounded = round_half_up_cents(
                ledger.cumulative_scaled(start_month - _ONE_DAY)
            )
            amounts: list[int] = []
            for end in month_ends:
                rounded = round_half_up_cents(ledger.cumulative_scaled(end))
                amounts.append(rounded - prev_rounded)
                prev_rounded = rounded
            result[txn_id] = amounts
        return result
