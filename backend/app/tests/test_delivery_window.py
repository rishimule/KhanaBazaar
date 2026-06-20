# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from datetime import date

import pytest

from app.utils.delivery_window import (
    DeliveryWindow,
    format_delivery_window,
    validate_preferred_window,
)

TODAY = date(2026, 6, 20)  # a Saturday


def test_enum_values():
    assert DeliveryWindow.Morning.value == "morning"
    assert DeliveryWindow.Afternoon.value == "afternoon"
    assert DeliveryWindow.Evening.value == "evening"


@pytest.mark.parametrize(
    "window,expected",
    [
        ("morning", "Sat 20 Jun · Morning (7–11 AM)"),
        ("afternoon", "Sat 20 Jun · Afternoon (11 AM – 3 PM)"),
        ("evening", "Sat 20 Jun · Evening (3–9 PM)"),
    ],
)
def test_format_delivery_window(window, expected):
    assert format_delivery_window(TODAY, window) == expected


def test_validate_accepts_valid_pair_within_horizon():
    validate_preferred_window(TODAY, "morning", today=TODAY)
    validate_preferred_window(date(2026, 6, 26), "evening", today=TODAY)  # today+6


def test_validate_accepts_both_none():
    validate_preferred_window(None, None, today=TODAY)


@pytest.mark.parametrize("d,window", [(TODAY, None), (None, "morning")])
def test_validate_rejects_only_one(d, window):
    with pytest.raises(ValueError, match="preferred_delivery_incomplete"):
        validate_preferred_window(d, window, today=TODAY)


def test_validate_rejects_unknown_window():
    with pytest.raises(ValueError, match="preferred_delivery_window_invalid"):
        validate_preferred_window(TODAY, "night", today=TODAY)


def test_validate_rejects_past_date():
    with pytest.raises(ValueError, match="preferred_delivery_date_in_past"):
        validate_preferred_window(date(2026, 6, 19), "morning", today=TODAY)


def test_validate_rejects_beyond_horizon():
    with pytest.raises(ValueError, match="preferred_delivery_date_beyond_horizon"):
        validate_preferred_window(date(2026, 6, 27), "morning", today=TODAY)  # today+7
