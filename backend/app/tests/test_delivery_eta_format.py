# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest

from app.utils.delivery_eta import format_delivery_eta


@pytest.mark.parametrize(
    "low,high,expected",
    [
        (30, 45, "30–45 min"),
        (45, 45, "45 min"),
        (120, 240, "2–4 hours"),
        (60, 60, "1 hour"),
        (90, 120, "90–120 min"),   # 90 not whole hours -> minutes
        (1440, 2880, "1–2 days"),
        (2880, 5760, "2–4 days"),
        (1440, 1440, "1 day"),
    ],
)
def test_format_delivery_eta(low: int, high: int, expected: str) -> None:
    assert format_delivery_eta(low, high) == expected
