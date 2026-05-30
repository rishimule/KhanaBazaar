# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Human-readable formatting for a delivery-time window expressed in minutes.

Rule: pick the largest unit (days, then hours, then minutes) in which BOTH
bounds are whole numbers; otherwise fall to the next smaller unit. Equal
bounds collapse to a single value with singular/plural unit.
"""

_MINUTES_PER_HOUR = 60
_MINUTES_PER_DAY = 60 * 24


def _unit(low: int, high: int) -> tuple[int, int, str, str]:
    if low % _MINUTES_PER_DAY == 0 and high % _MINUTES_PER_DAY == 0:
        return low // _MINUTES_PER_DAY, high // _MINUTES_PER_DAY, "day", "days"
    if low % _MINUTES_PER_HOUR == 0 and high % _MINUTES_PER_HOUR == 0:
        return low // _MINUTES_PER_HOUR, high // _MINUTES_PER_HOUR, "hour", "hours"
    return low, high, "min", "min"


def format_delivery_eta(min_minutes: int, max_minutes: int) -> str:
    low, high, singular, plural = _unit(min_minutes, max_minutes)
    if low == high:
        unit = singular if low == 1 else plural
        return f"{low} {unit}"
    return f"{low}–{high} {plural}"
