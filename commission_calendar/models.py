"""Data model for subscription commission snapshots.

All types are immutable value objects. A snapshot is a complete, read-only
view of subscriptions used as the sole input to commission calculation.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Tuple


class Window(Enum):
    """Commission window length in subscription months, or lifetime."""

    MONTHS_6 = 6
    MONTHS_12 = 12
    MONTHS_24 = 24
    LIFETIME = 0  # sentinel: no window end


@dataclass(frozen=True)
class PriceRecord:
    """Monthly recurring revenue (cents, non-negative) effective from a date."""

    effective_date: date
    mrc_cents: int


@dataclass(frozen=True)
class Subscription:
    """A single subscription in the snapshot.

    deal_date is both the deal date and the service start date.
    price_records start at deal_date; effective dates are unique per
    subscription. cancel_date ends eligibility at 00:00 that day.
    """

    txn_id: str
    partner_id: str
    deal_date: date
    window: Window
    price_records: Tuple[PriceRecord, ...]
    cancel_date: Optional[date] = None


@dataclass(frozen=True)
class Snapshot:
    """Complete, immutable set of subscriptions."""

    subscriptions: Tuple[Subscription, ...]

    def replace(self, **changes) -> "Snapshot":
        return dataclasses.replace(self, **changes)
