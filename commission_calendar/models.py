"""Data model for subscription snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

VALID_WINDOWS = (6, 12, 24)


@dataclass(frozen=True)
class PriceRecord:
    """Monthly recurring revenue (cents) effective from a calendar day."""

    effective_date: date
    mrr_cents: int


@dataclass(frozen=True)
class Subscription:
    """A single immutable subscription snapshot row.

    ``deal_date`` is both the deal date and the service start date.
    ``window_months`` is 6, 12, 24, or None for lifetime.
    ``prices`` starts at ``deal_date`` and has no duplicate effective dates.
    """

    txn_id: str
    partner_id: str
    deal_date: date
    window_months: int | None
    prices: tuple[PriceRecord, ...]
    cancel_date: date | None = None


def validate_snapshot(subscriptions: list[Subscription]) -> None:
    """Validate a full snapshot; raise ValueError on any inconsistency."""
    seen_txn: set[str] = set()
    for sub in subscriptions:
        if not sub.txn_id or not sub.txn_id.isascii():
            raise ValueError(f"txn_id must be non-empty ASCII: {sub.txn_id!r}")
        if sub.txn_id in seen_txn:
            raise ValueError(f"duplicate txn_id: {sub.txn_id!r}")
        seen_txn.add(sub.txn_id)
        if not sub.partner_id:
            raise ValueError(f"{sub.txn_id!r}: partner_id must be non-empty")
        if sub.window_months not in (*VALID_WINDOWS, None):
            raise ValueError(
                f"{sub.txn_id!r}: window_months must be 6, 12, 24 or None"
            )
        if not sub.prices:
            raise ValueError(f"{sub.txn_id!r}: at least one price record required")
        if sub.prices[0].effective_date != sub.deal_date:
            raise ValueError(
                f"{sub.txn_id!r}: first price record must start at deal_date"
            )
        seen_dates: set[date] = set()
        for rec in sub.prices:
            if rec.effective_date in seen_dates:
                raise ValueError(
                    f"{sub.txn_id!r}: duplicate price effective date "
                    f"{rec.effective_date}"
                )
            seen_dates.add(rec.effective_date)
            if rec.mrr_cents < 0:
                raise ValueError(f"{sub.txn_id!r}: negative mrr_cents")
        if len(sub.prices) != len(seen_dates) or sub.prices != tuple(
            sorted(sub.prices, key=lambda r: r.effective_date)
        ):
            raise ValueError(f"{sub.txn_id!r}: price records must be sorted")
        if sub.cancel_date is not None and sub.cancel_date < sub.deal_date:
            raise ValueError(f"{sub.txn_id!r}: cancel_date before deal_date")
