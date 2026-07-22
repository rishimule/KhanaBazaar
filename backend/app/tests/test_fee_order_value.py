# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Integration tests for the Order Value % (postpaid + security deposit) fee model."""
import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.base import User, UserRole
from app.models.commerce import Order, OrderStatus
from app.models.notification import NotificationType
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeInvoice,
    FeeModel,
    InvoiceStatus,
    ServiceFeeConfig,
)
from app.models.profile import CustomerProfile
from tests._helpers import make_address


class _Env:
    def __init__(self, *, store, service_id, customer_profile_id, address_id):
        self.store = store
        self.service_id = service_id
        self.customer_profile_id = customer_profile_id
        self.address_id = address_id


@pytest_asyncio.fixture
async def ov_env(session: AsyncSession, approved_seller_with_store) -> _Env:
    bundle = approved_seller_with_store
    user = User(email=f"c-{uuid.uuid4().hex[:8]}@x.test", role=UserRole.Customer)
    session.add(user)
    await session.flush()
    profile = CustomerProfile(user_id=user.id, first_name="Cust")
    session.add(profile)
    await session.flush()
    addr = Address(**make_address())
    session.add(addr)
    await session.flush()
    await session.commit()
    return _Env(
        store=bundle.store,
        service_id=bundle.service_id,
        customer_profile_id=profile.id,
        address_id=addr.id,
    )


async def _ov_cfg(
    session: AsyncSession,
    service_id: int,
    *,
    percent: float = 2.0,
    min_deposit: float = 500.0,
    billing_day: int = 5,
    payment_days: int = 7,
) -> ServiceFeeConfig:
    cfg = ServiceFeeConfig(
        service_id=service_id,
        order_value_enabled=True,
        order_value_percent=percent,
        order_value_min_deposit=min_deposit,
        order_value_billing_day=billing_day,
        order_value_payment_days=payment_days,
    )
    session.add(cfg)
    await session.flush()
    return cfg


async def _ov_arr(
    session: AsyncSession,
    env: _Env,
    *,
    status: ArrangementStatus = ArrangementStatus.Active,
    deposit: float = 500.0,
    activated_on: date | None = None,
    last_billed_period_end: date | None = None,
) -> FeeArrangement:
    arr = FeeArrangement(
        store_id=env.store.id,
        service_id=env.service_id,
        model=FeeModel.OrderValuePercent,
        status=status,
        security_deposit_amount=deposit,
        order_value_activated_on=activated_on,
        last_billed_period_end=last_billed_period_end,
    )
    session.add(arr)
    await session.flush()
    return arr


async def _ov_order(
    session: AsyncSession,
    env: _Env,
    *,
    total: float,
    status: OrderStatus,
    placed_at: datetime,
) -> Order:
    order = Order(
        customer_profile_id=env.customer_profile_id,
        store_id=env.store.id,
        service_id=env.service_id,
        service_name_snapshot="Grocery",
        delivery_address_id=env.address_id,
        status=status,
        subtotal=total,
        delivery_fee=0.0,
        tax=0.0,
        total=total,
        delivery_address_snapshot="addr",
        placed_at=placed_at,
    )
    session.add(order)
    await session.flush()
    return order


def test_order_value_notification_types_present() -> None:
    assert NotificationType.FeeInvoiceRaised.value == "fee_invoice_raised"
    assert NotificationType.FeeInvoiceOverdue.value == "fee_invoice_overdue"


def test_invoice_model_and_enum_shape() -> None:
    assert {s.value for s in InvoiceStatus} == {
        "pending",
        "paid",
        "overdue",
        "waived",
        "cancelled",
    }
    inv = FeeInvoice(
        arrangement_id=1,
        store_id=1,
        service_id=1,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        sales_total=5000.0,
        fee_percent_snapshot=2.0,
        amount_due=100.0,
        status=InvoiceStatus.Pending,
        issued_on=date(2026, 2, 5),
        due_date=date(2026, 2, 12),
        suspend_after=date(2026, 2, 14),
    )
    assert inv.amount_due == 100.0
    assert inv.status == InvoiceStatus.Pending

    # new config + arrangement columns exist with expected defaults
    assert ServiceFeeConfig(service_id=1).order_value_payment_days == 7
    arr_fields = FeeArrangement.model_fields
    assert "order_value_activated_on" in arr_fields
    assert "last_billed_period_end" in arr_fields


def _at(d: date) -> datetime:
    """Midday UTC on the given date — unambiguously inside the same day in IST."""
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_compute_sales_delivered_in_period(
    session: AsyncSession, ov_env: _Env
) -> None:
    from app.services.fee_order_value import compute_order_value_sales

    env = ov_env
    # In-period delivered: 3000 + 2000 = 5000
    await _ov_order(session, env, total=3000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 10)))
    await _ov_order(session, env, total=2000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 25)))
    # In-period but not delivered (excluded)
    await _ov_order(session, env, total=999.0, status=OrderStatus.Cancelled, placed_at=_at(date(2026, 1, 15)))
    await _ov_order(session, env, total=888.0, status=OrderStatus.Pending, placed_at=_at(date(2026, 1, 16)))
    # Delivered but out of period (excluded)
    await _ov_order(session, env, total=500.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 2, 3)))
    await session.commit()

    total = await compute_order_value_sales(
        session, env.store.id, env.service_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert total == 5000.0
