# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from decimal import Decimal

import pytest

from app.utils.currency import format_inr


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, "₹0.00"),
        (1, "₹1.00"),
        (12.5, "₹12.50"),
        (1234.5, "₹1,234.50"),
        (1234567.89, "₹12,34,567.89"),
        (Decimal("99.99"), "₹99.99"),
        (Decimal("100000"), "₹1,00,000.00"),
    ],
)
def test_format_inr_groups_indian_lakh_crore(value, expected):
    assert format_inr(value) == expected


def test_format_inr_rejects_negative():
    with pytest.raises(ValueError):
        format_inr(-1)
