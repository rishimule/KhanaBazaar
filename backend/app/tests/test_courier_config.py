# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Courier settings. Builds `Settings` directly (as test_config.py does) so the
shared singleton is never mutated."""
import pytest
from pydantic import ValidationError

from app.api.orders import _status_filter_for
from app.core.config import Settings
from app.models.commerce import ACTIVE_ORDER_STATUSES

_REQUIRED = {
    "JWT_SECRET": "test-secret",
    "OTP_PEPPER": "test-pepper",
    "DATABASE_URL": "postgresql+asyncpg://x@localhost/x",
    "REDIS_URL": "redis://localhost:6379/0",
}


def _make(**overrides: object) -> Settings:
    return Settings(_env_file=None, **_REQUIRED, **overrides)  # type: ignore[arg-type]


def test_courier_defaults() -> None:
    s = _make()
    assert s.COURIER_MAX_RADIUS_KM == 3500.0
    assert s.COURIER_MAX_QUOTE_VERSIONS == 5
    assert s.COURIER_REMINDER_HOURS == 24
    assert s.COURIER_ARRIVAL_GRACE_DAYS == 1
    assert s.COURIER_REFUND_REMINDER_DAYS == [1, 3, 7]
    assert s.COURIER_STALE_DAYS == 3
    assert (s.COURIER_QUIET_START_HOUR, s.COURIER_QUIET_END_HOUR) == (21, 9)


@pytest.mark.parametrize(
    "field",
    [
        "COURIER_MAX_RADIUS_KM",
        "COURIER_MAX_QUOTE_VERSIONS",
        "COURIER_REMINDER_HOURS",
        "COURIER_ARRIVAL_GRACE_DAYS",
        "COURIER_STALE_DAYS",
    ],
)
def test_zero_fails_startup(field: str) -> None:
    with pytest.raises(ValidationError):
        _make(**{field: 0})


def test_refund_reminder_days_are_sorted_and_positive() -> None:
    assert _make(COURIER_REFUND_REMINDER_DAYS=[7, 1, 3, 3]).COURIER_REFUND_REMINDER_DAYS == [1, 3, 7]
    with pytest.raises(ValidationError):
        _make(COURIER_REFUND_REMINDER_DAYS=[0, 3])
    with pytest.raises(ValidationError):
        _make(COURIER_REFUND_REMINDER_DAYS=[])


def test_active_filter_uses_the_shared_list() -> None:
    assert _status_filter_for("active") == ACTIVE_ORDER_STATUSES


def test_dashboard_counts_cover_every_status() -> None:
    # The seller dashboard fills these with `hasattr`, so a missing field
    # silently drops orders in that status from the donut total.
    from app.models.commerce import OrderStatus
    from app.schemas.sellers import OrderStatusCounts

    assert set(OrderStatusCounts.model_fields) == {s.value for s in OrderStatus}
