# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Preferred delivery window: a soft customer hint (date + time-of-day band).

Fixed, global windows in IST. Mirrored on the frontend by
``frontend/src/lib/deliveryWindows.ts`` — keep the keys + hour labels in sync.
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
HORIZON_DAYS = 6  # today + 6 days = a 7-day selectable range


class DeliveryWindow(str, enum.Enum):
    Morning = "morning"
    Afternoon = "afternoon"
    Evening = "evening"


# key -> (display name, hour label)
_WINDOW_META: dict[str, tuple[str, str]] = {
    "morning": ("Morning", "7–11 AM"),
    "afternoon": ("Afternoon", "11 AM – 3 PM"),
    "evening": ("Evening", "3–9 PM"),
}

# Guard against the enum and the label map drifting apart (single source of
# truth for the three valid window keys).
assert {w.value for w in DeliveryWindow} == set(_WINDOW_META)


def ist_today() -> date:
    """Today's calendar date in IST (the scheduling baseline)."""
    return datetime.now(IST).date()


def format_delivery_window(d: date, window: str) -> str:
    """Human label, e.g. ``"Sat 20 Jun · Evening (3–9 PM)"``. English-only."""
    name, hours = _WINDOW_META[window]
    return f"{d:%a} {d.day} {d:%b} · {name} ({hours})"


def validate_preferred_window(
    d: date | None, window: str | None, *, today: date
) -> None:
    """Raise ``ValueError`` on an invalid preferred-window pair.

    Soft rules only: both-or-neither presence, a known window key, and a date
    within ``[today, today + HORIZON_DAYS]``. No store-hours, capacity, or
    time-of-day checks (the same-day "ended window" rule is frontend-only).
    """
    if (d is None) != (window is None):
        raise ValueError("preferred_delivery_incomplete")
    if d is None:
        return
    if window not in _WINDOW_META:
        raise ValueError("preferred_delivery_window_invalid")
    if d < today:
        raise ValueError("preferred_delivery_date_in_past")
    if d > today + timedelta(days=HORIZON_DAYS):
        raise ValueError("preferred_delivery_date_beyond_horizon")
