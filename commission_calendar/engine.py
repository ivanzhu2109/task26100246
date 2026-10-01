"""Commission calculation engine.

Exact arithmetic: every accrual is kept as a Fraction of a cent and only
rounded (half-up) at calendar-month ends, on the cumulative amount since
the original service start. Daily or per-segment rounding never happens.

Key exactness shortcut: within a subscription month where the monthly
recurring revenue (MRC) is constant for the whole month, the month's
accrual is exactly mrc * rate, independent of the month's day count.
Day-count denominators only matter for partial months (price change,
cancellation, window expiry, or the queried cut-off day).
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

from .calendar import add_months_clamped, month_index_containing
from .models import Snapshot, Subscription, Window

_TIER_THRESHOLD = 10  # first N deals per partner
_TIER_LOW = Fraction(10, 100)
_TIER_HIGH = Fraction(15, 100)

_ONE_DAY = timedelta(days=1)


def round_half_up(value: Fraction) -> int:
    """Round a non-negative exact value to integer cents, halves away from zero."""
    if value < 0:
        raise ValueError("commission values are never negative")
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


@dataclass(frozen=True)
class QueryResult:
    """Per-subscription, per-calendar-month commission in integer cents."""

    months: Tuple[date, ...]  # first day of each queried calendar month
    amounts: Dict[str, List[int]]  # txn_id -> one entry per month

    def total(self, txn_id: str) -> int:
        return sum(self.amounts[txn_id])


def _termination_date(sub: Subscription) -> Optional[date]:
    """First day with no commission: earlier of window end and cancel date."""
    end: Optional[date] = None
    if sub.window is not Window.LIFETIME:
        end = add_months_clamped(sub.deal_date, sub.window.value)
    if sub.cancel_date is not None and (end is None or sub.cancel_date < end):
        end = sub.cancel_date
    return end


def _segment_accrual(
    start: date, seg_begin: date, seg_end: date, mrc: int, rate: Fraction
) -> Fraction:
    """Exact accrual of one constant-MRC stretch over [seg_begin, seg_end)."""
    if mrc == 0 or seg_end <= seg_begin:
        return Fraction(0)
    k0 = month_index_containing(start, seg_begin)
    k1 = month_index_containing(start, seg_end - _ONE_DAY)
    if k0 == k1:
        days = (seg_end - seg_begin).days
        dim = (add_months_clamped(start, k0 + 1) - add_months_clamped(start, k0)).days
        return Fraction(days * mrc, dim) * rate
    # First partial subscription month.
    first_end = add_months_clamped(start, k0 + 1)
    dim0 = (first_end - add_months_clamped(start, k0)).days
    total = Fraction((first_end - seg_begin).days * mrc, dim0) * rate
    # Fully covered subscription months: exact accrual is mrc * rate each.
    if k1 - k0 > 1:
        total += (k1 - k0 - 1) * mrc * rate
    # Last partial subscription month.
    last_begin = add_months_clamped(start, k1)
    dim1 = (add_months_clamped(start, k1 + 1) - last_begin).days
    total += Fraction((seg_end - last_begin).days * mrc, dim1) * rate
    return total


class _PreparedSubscription:
    """Precomputed exact accrual checkpoints for one subscription."""

    __slots__ = ("start", "termination", "rate", "seg_starts", "seg_mrc", "seg_cum")

    def __init__(self, sub: Subscription, rate: Fraction) -> None:
        self.start = sub.deal_date
        self.rate = rate
        self.termination = _termination_date(sub)

        # Price segments clipped to the eligible interval [start, termination).
        records = sorted(sub.price_records, key=lambda r: r.effective_date)
        seg_starts: List[date] = []
        seg_mrc: List[int] = []
        seg_cum: List[Fraction] = []  # exact cumulative accrual at each segment start
        cum = Fraction(0)
        for i, rec in enumerate(records):
            seg_begin = rec.effective_date
            if self.termination is not None and seg_begin >= self.termination:
                break
            seg_starts.append(seg_begin)
            seg_mrc.append(rec.mrc_cents)
            seg_cum.append(cum)
            if i + 1 < len(records):
                seg_end = records[i + 1].effective_date
                if self.termination is not None and self.termination < seg_end:
                    seg_end = self.termination
            elif self.termination is not None:
                seg_end = self.termination
            else:
                seg_end = None  # open-ended final segment
            if seg_end is not None:
                cum += _segment_accrual(sub.deal_date, seg_begin, seg_end, rec.mrc_cents, rate)
        self.seg_starts = seg_starts
        self.seg_mrc = seg_mrc
        self.seg_cum = seg_cum

    def cumulative(self, day: date) -> Fraction:
        """Exact accrued commission for eligible days in [start, day)."""
        if not self.seg_starts or day <= self.start:
            return Fraction(0)
        if self.termination is not None and day > self.termination:
            day = self.termination
        idx = bisect_right(self.seg_starts, day) - 1
        if idx < 0:
            return Fraction(0)
        if self.seg_starts[idx] == day:
            return self.seg_cum[idx]
        return self.seg_cum[idx] + _segment_accrual(
            self.start, self.seg_starts[idx], day, self.seg_mrc[idx], self.rate
        )


def _validate(sub: Subscription) -> None:
    if not sub.txn_id or not sub.txn_id.isascii():
        raise ValueError(f"txn_id must be non-empty ASCII: {sub.txn_id!r}")
    if not sub.partner_id:
        raise ValueError(f"partner_id must be non-empty: {sub.txn_id!r}")
    if not isinstance(sub.window, Window):
        raise ValueError(f"unknown window: {sub.window!r}")
    if not sub.price_records:
        raise ValueError(f"subscription {sub.txn_id!r} has no price records")
    dates = [r.effective_date for r in sub.price_records]
    if len(set(dates)) != len(dates):
        raise ValueError(f"duplicate price effective dates in {sub.txn_id!r}")
    if min(dates) != sub.deal_date:
        raise ValueError(f"price records must start at deal date in {sub.txn_id!r}")
    for rec in sub.price_records:
        if not isinstance(rec.mrc_cents, int) or rec.mrc_cents < 0:
            raise ValueError(f"mrc must be a non-negative int in {sub.txn_id!r}")
    if sub.cancel_date is not None and sub.cancel_date < sub.deal_date:
        raise ValueError(f"cancel_date before deal_date in {sub.txn_id!r}")


class CommissionCalendar:
    """Computes commissions from an immutable snapshot; all state in memory."""

    def __init__(self, snapshot: Snapshot) -> None:
        subs = list(snapshot.subscriptions)
        seen = set()
        for sub in subs:
            _validate(sub)
            if sub.txn_id in seen:
                raise ValueError(f"duplicate txn_id: {sub.txn_id!r}")
            seen.add(sub.txn_id)

        # Tier assignment per partner: deal date ascending, txn_id ASCII
        # lexicographic as tie-breaker. Cancelled subscriptions keep their slot.
        rate_by_txn: Dict[str, Fraction] = {}
        by_partner: Dict[str, List[Subscription]] = {}
        for sub in subs:
            by_partner.setdefault(sub.partner_id, []).append(sub)
        for partner_subs in by_partner.values():
            partner_subs.sort(key=lambda s: (s.deal_date, s.txn_id))
            for rank, sub in enumerate(partner_subs):
                rate_by_txn[sub.txn_id] = _TIER_LOW if rank < _TIER_THRESHOLD else _TIER_HIGH

        self._prepared: Dict[str, _PreparedSubscription] = {
            sub.txn_id: _PreparedSubscription(sub, rate_by_txn[sub.txn_id]) for sub in subs
        }

    def query(self, start_month: date, end_month: date) -> QueryResult:
        """Commission per subscription per calendar month in [start_month, end_month)."""
        if start_month.day != 1 or end_month.day != 1:
            raise ValueError("query bounds must be first day of a calendar month")
        if end_month <= start_month:
            raise ValueError("end_month must be after start_month")

        months: List[date] = []
        cursor = start_month
        while cursor < end_month:
            months.append(cursor)
            cursor = add_months_clamped(cursor, 1)
        bounds = months + [end_month]

        amounts: Dict[str, List[int]] = {}
        for txn_id, prepared in self._prepared.items():
            rounded = [round_half_up(prepared.cumulative(b)) for b in bounds]
            amounts[txn_id] = [rounded[i + 1] - rounded[i] for i in range(len(months))]
        return QueryResult(months=tuple(months), amounts=amounts)
