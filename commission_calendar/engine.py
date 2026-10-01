"""Exact accrual engine for one subscription.

All amounts are kept as exact integers in scaled units: one cent equals
``SCALE`` units, where SCALE = 100 * lcm(28, 29, 30, 31). A subscription
month always has 28..31 days, so every daily accrual
``mrr * rate_pct / (100 * days_in_month)`` is an exact integer in these
units and cumulative sums never lose precision.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta

from .calendar import add_months_clamped, boundary_index
from .models import Subscription

LCM_DAYS = 377580  # lcm(28, 29, 30, 31)
SCALE = 100 * LCM_DAYS  # scaled units per cent

_ONE_DAY = timedelta(days=1)


def round_half_up_cents(cum_scaled: int) -> int:
    """Round a scaled cumulative amount to integer cents, half up."""
    return (cum_scaled + SCALE // 2) // SCALE


class SubscriptionLedger:
    """Precomputed exact accrual data for a single subscription."""

    def __init__(self, subscription: Subscription, rate_pct: int) -> None:
        self.start = subscription.deal_date
        self.rate_pct = rate_pct
        ends: list[date] = []
        if subscription.window_months is not None:
            ends.append(add_months_clamped(self.start, subscription.window_months))
        if subscription.cancel_date is not None:
            ends.append(subscription.cancel_date)
        # First day with no eligibility; the termination day itself earns 0.
        self.term_end: date | None = min(ends) if ends else None
        self._price_dates = [r.effective_date for r in subscription.prices]
        self._price_mrr = [r.mrr_cents for r in subscription.prices]
        # cum[k] = exact scaled accrual over [start, boundary_k); extended lazily.
        self._cum: list[int] = [0]

    def _boundary(self, k: int) -> date:
        return add_months_clamped(self.start, k)

    def _segment_sum(self, lo: date, hi: date, dim: int) -> int:
        """Exact scaled accrual over days [lo, hi) within a month of ``dim`` days."""
        if hi <= lo:
            return 0
        factor = self.rate_pct * (LCM_DAYS // dim)
        total_mrr_days = 0
        i = bisect_right(self._price_dates, lo) - 1
        d = lo
        while d < hi:
            nxt = self._price_dates[i + 1] if i + 1 < len(self._price_dates) else None
            seg_end = hi if nxt is None or nxt > hi else nxt
            total_mrr_days += self._price_mrr[i] * (seg_end - d).days
            d = seg_end
            i += 1
        return total_mrr_days * factor

    def _ensure_cum(self, k: int) -> None:
        while len(self._cum) <= k:
            j = len(self._cum) - 1
            b_j = self._boundary(j)
            b_next = self._boundary(j + 1)
            hi = b_next
            if self.term_end is not None and self.term_end < hi:
                hi = self.term_end
            dim = (b_next - b_j).days
            inc = self._segment_sum(b_j, hi, dim) if b_j < hi else 0
            self._cum.append(self._cum[-1] + inc)

    def cumulative_scaled(self, day: date) -> int:
        """Exact accrued commission from service start up to and including ``day``."""
        if day < self.start:
            return 0
        k = boundary_index(self.start, day)
        self._ensure_cum(k)
        b_k = self._boundary(k)
        hi = day + _ONE_DAY
        b_next = self._boundary(k + 1)
        if b_next < hi:
            hi = b_next
        if self.term_end is not None and self.term_end < hi:
            hi = self.term_end
        dim = (b_next - b_k).days
        return self._cum[k] + self._segment_sum(b_k, hi, dim)
