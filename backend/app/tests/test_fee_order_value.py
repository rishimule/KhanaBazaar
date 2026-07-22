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
    FeePayment,
    FeePaymentKind,
    FeePaymentStatus,
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


async def _invoices(session: AsyncSession, arr_id: int) -> list[FeeInvoice]:
    return list(
        (
            await session.exec(
                select(FeeInvoice).where(FeeInvoice.arrangement_id == arr_id)
            )
        ).all()
    )


@pytest.mark.asyncio
async def test_generate_invoice_normal_month(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import generate_order_value_invoices

    env = ov_env
    await _ov_cfg(session, env.service_id, percent=2.0, billing_day=5)
    arr = await _ov_arr(session, env, activated_on=date(2026, 1, 1))
    await _ov_order(session, env, total=5000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 15)))
    await session.commit()

    created = await generate_order_value_invoices(session, date(2026, 2, 5))
    await session.commit()

    assert created == 1
    invs = await _invoices(session, arr.id)
    assert len(invs) == 1
    inv = invs[0]
    assert inv.period_start == date(2026, 1, 1)
    assert inv.period_end == date(2026, 1, 31)
    assert inv.sales_total == 5000.0
    assert inv.amount_due == 100.0
    assert inv.status == InvoiceStatus.Pending
    assert inv.issued_on == date(2026, 2, 5)
    assert inv.due_date == date(2026, 2, 12)  # +7 payment days
    assert inv.suspend_after == date(2026, 2, 14)  # +2 grace default
    await session.refresh(arr)
    assert arr.balance == 100.0
    assert arr.last_billed_period_end == date(2026, 1, 31)


@pytest.mark.asyncio
async def test_generate_invoice_zero_sales_auto_paid(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import generate_order_value_invoices

    env = ov_env
    await _ov_cfg(session, env.service_id, percent=2.0, billing_day=5)
    arr = await _ov_arr(session, env, activated_on=date(2026, 1, 1))
    await session.commit()

    created = await generate_order_value_invoices(session, date(2026, 2, 5))
    await session.commit()

    assert created == 1
    inv = (await _invoices(session, arr.id))[0]
    assert inv.amount_due == 0.0
    assert inv.status == InvoiceStatus.Paid
    assert inv.paid_at is not None
    await session.refresh(arr)
    assert arr.balance == 0.0  # zero invoice never touches balance


@pytest.mark.asyncio
async def test_generate_invoice_idempotent(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import generate_order_value_invoices

    env = ov_env
    await _ov_cfg(session, env.service_id, billing_day=5)
    arr = await _ov_arr(session, env, activated_on=date(2026, 1, 1))
    await _ov_order(session, env, total=1000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 15)))
    await session.commit()

    first = await generate_order_value_invoices(session, date(2026, 2, 5))
    await session.commit()
    second = await generate_order_value_invoices(session, date(2026, 2, 5))
    await session.commit()

    assert first == 1
    assert second == 0
    assert len(await _invoices(session, arr.id)) == 1


@pytest.mark.asyncio
async def test_generate_invoice_partial_first_month(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import generate_order_value_invoices

    env = ov_env
    await _ov_cfg(session, env.service_id, percent=2.0, billing_day=5)
    arr = await _ov_arr(session, env, activated_on=date(2026, 1, 20))
    # Before activation -> excluded from the clipped period.
    await _ov_order(session, env, total=4000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 10)))
    # After activation -> counted.
    await _ov_order(session, env, total=1000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 25)))
    await session.commit()

    await generate_order_value_invoices(session, date(2026, 2, 5))
    await session.commit()

    inv = (await _invoices(session, arr.id))[0]
    assert inv.period_start == date(2026, 1, 20)
    assert inv.period_end == date(2026, 1, 31)
    assert inv.sales_total == 1000.0
    assert inv.amount_due == 20.0


@pytest.mark.asyncio
async def test_generate_invoice_only_on_billing_day(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import generate_order_value_invoices

    env = ov_env
    await _ov_cfg(session, env.service_id, billing_day=5)
    arr = await _ov_arr(session, env, activated_on=date(2026, 1, 1))
    await session.commit()

    created = await generate_order_value_invoices(session, date(2026, 2, 4))  # not the 5th
    await session.commit()
    assert created == 0
    assert len(await _invoices(session, arr.id)) == 0


# ─── Slice C: opt-in + deposit activation ────────────────────────────────


async def _freebie_arr(session: AsyncSession, env: _Env) -> FeeArrangement:
    arr = FeeArrangement(
        store_id=env.store.id,
        service_id=env.service_id,
        model=FeeModel.Freebie,
        status=ArrangementStatus.Trial,
    )
    session.add(arr)
    await session.flush()
    return arr


@pytest.mark.asyncio
async def test_opt_in_below_min_deposit_raises(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_lifecycle import FeeError
    from app.services.fee_order_value import opt_into_order_value

    env = ov_env
    await _ov_cfg(session, env.service_id, min_deposit=500.0)
    arr = await _freebie_arr(session, env)
    with pytest.raises(FeeError, match="below_min_deposit"):
        await opt_into_order_value(session, arr, 100.0)


@pytest.mark.asyncio
async def test_opt_in_not_enabled_raises(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_lifecycle import FeeError
    from app.services.fee_order_value import opt_into_order_value

    env = ov_env
    session.add(ServiceFeeConfig(service_id=env.service_id, order_value_enabled=False))
    await session.flush()
    arr = await _freebie_arr(session, env)
    with pytest.raises(FeeError, match="order_value_not_offerable"):
        await opt_into_order_value(session, arr, 1000.0)


@pytest.mark.asyncio
async def test_opt_in_creates_pending_deposit(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import opt_into_order_value

    env = ov_env
    await _ov_cfg(session, env.service_id, min_deposit=500.0)
    arr = await _freebie_arr(session, env)
    payment = await opt_into_order_value(session, arr, 800.0)
    await session.commit()

    assert arr.status == ArrangementStatus.PendingActivation
    assert arr.model == FeeModel.OrderValuePercent
    assert payment.kind == FeePaymentKind.SecurityDeposit
    assert payment.amount == 800.0
    assert payment.status == FeePaymentStatus.Pending


@pytest.mark.asyncio
async def test_confirm_deposit_activates(session: AsyncSession, ov_env: _Env) -> None:
    from app.models.notification import NotificationType
    from app.services.fee_order_value import (
        confirm_order_value_deposit,
        opt_into_order_value,
    )

    env = ov_env
    await _ov_cfg(session, env.service_id, min_deposit=500.0)
    arr = await _freebie_arr(session, env)
    payment = await opt_into_order_value(session, arr, 800.0)
    await session.commit()

    result_arr, notif = await confirm_order_value_deposit(
        session, payment, admin_user_id=1, today=date(2026, 1, 20)
    )
    await session.commit()

    assert result_arr.status == ArrangementStatus.Active
    assert result_arr.security_deposit_amount == 800.0
    assert result_arr.order_value_activated_on == date(2026, 1, 20)
    assert result_arr.last_billed_period_end is None
    assert notif == NotificationType.FeeActivated
    await session.refresh(payment)
    assert payment.status == FeePaymentStatus.Confirmed
    assert payment.confirmed_by_admin_id == 1


# ─── Slice C2: seller + admin API ────────────────────────────────────────


async def _persist_test_admin(session: AsyncSession) -> None:
    if await session.get(User, 99001) is None:
        session.add(
            User(id=99001, email="admin-ov@kb.com", role=UserRole.Admin, is_active=True)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_api_opt_in_then_admin_confirm_activates(
    client, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    from app import app
    from app.core.security import get_current_seller

    bundle = approved_seller_with_store
    sid = bundle.service_id
    await _persist_test_admin(session)
    session.add(
        ServiceFeeConfig(
            service_id=sid, order_value_enabled=True, order_value_percent=2.0,
            order_value_min_deposit=500.0, order_value_billing_day=5,
        )
    )
    session.add(
        FeeArrangement(
            store_id=bundle.store.id, service_id=sid,
            model=FeeModel.Freebie, status=ArrangementStatus.Trial,
        )
    )
    await session.commit()

    app.dependency_overrides[get_current_seller] = lambda: bundle.user
    try:
        r = await client.post(
            f"/api/v1/sellers/me/plan/{sid}/order-value/opt-in",
            json={"deposit_amount": 800.0},
        )
        assert r.status_code == 200, r.text
        payment_id = r.json()["payment_id"]
    finally:
        app.dependency_overrides.pop(get_current_seller, None)

    # arrangement is pending until admin confirms
    arr = (
        await session.exec(
            select(FeeArrangement).where(FeeArrangement.store_id == bundle.store.id)
        )
    ).one()
    await session.refresh(arr)
    assert arr.status == ArrangementStatus.PendingActivation

    r2 = await client.post(
        f"/api/v1/admin/fees/payments/{payment_id}/confirm", headers=admin_auth_headers
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "active"

    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Active
    assert arr.security_deposit_amount == 800.0


# ─── Slice D: overdue sweep, suspension, reactivation ────────────────────


async def _mk_invoice(
    session: AsyncSession,
    env: _Env,
    arr: FeeArrangement,
    *,
    amount: float,
    status: InvoiceStatus,
    due_date: date,
    suspend_after: date,
) -> FeeInvoice:
    inv = FeeInvoice(
        arrangement_id=arr.id,
        store_id=env.store.id,
        service_id=env.service_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        sales_total=amount * 50,
        fee_percent_snapshot=2.0,
        amount_due=amount,
        status=status,
        issued_on=date(2026, 2, 5),
        due_date=due_date,
        suspend_after=suspend_after,
    )
    session.add(inv)
    arr.balance += amount
    session.add(arr)
    await session.flush()
    return inv


@pytest.mark.asyncio
async def test_sweep_marks_overdue(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import sweep_order_value_overdue

    env = ov_env
    arr = await _ov_arr(session, env)
    inv = await _mk_invoice(
        session, env, arr, amount=100.0, status=InvoiceStatus.Pending,
        due_date=date(2026, 2, 12), suspend_after=date(2026, 2, 14),
    )
    await session.commit()

    await sweep_order_value_overdue(session, date(2026, 2, 13))  # past due, before suspend
    await session.commit()

    await session.refresh(inv)
    await session.refresh(arr)
    assert inv.status == InvoiceStatus.Overdue
    assert arr.status == ArrangementStatus.Active  # not yet suspended


@pytest.mark.asyncio
async def test_sweep_suspends_after_grace(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import sweep_order_value_overdue

    env = ov_env
    arr = await _ov_arr(session, env)
    await _mk_invoice(
        session, env, arr, amount=100.0, status=InvoiceStatus.Overdue,
        due_date=date(2026, 2, 12), suspend_after=date(2026, 2, 14),
    )
    await session.commit()

    await sweep_order_value_overdue(session, date(2026, 2, 15))  # past suspend_after
    await session.commit()

    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Suspended
    assert arr.suspended_reason == "order_value_nonpayment"


@pytest.mark.asyncio
async def test_run_fee_sweep_generates_order_value_invoice(
    session: AsyncSession, ov_env: _Env
) -> None:
    from app.services.fee_lifecycle import run_fee_sweep

    env = ov_env
    await _ov_cfg(session, env.service_id, percent=2.0, billing_day=5)
    arr = await _ov_arr(session, env, activated_on=date(2026, 1, 1))
    await _ov_order(session, env, total=1000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 15)))
    await session.commit()

    await run_fee_sweep(session, today=date(2026, 2, 5))
    await session.commit()

    invs = await _invoices(session, arr.id)
    assert len(invs) == 1
    assert invs[0].amount_due == 20.0


async def _invoice_with_payment(
    session: AsyncSession,
    env: _Env,
    arr: FeeArrangement,
    *,
    amount: float,
    inv_status: InvoiceStatus,
    due_date: date = date(2026, 2, 12),
    suspend_after: date = date(2026, 2, 14),
) -> tuple[FeeInvoice, FeePayment]:
    inv = await _mk_invoice(
        session, env, arr, amount=amount, status=inv_status,
        due_date=due_date, suspend_after=suspend_after,
    )
    payment = FeePayment(
        arrangement_id=arr.id,
        kind=FeePaymentKind.OrderValueInvoice,
        amount=amount,
        status=FeePaymentStatus.Pending,
    )
    session.add(payment)
    await session.flush()
    inv.payment_id = payment.id
    session.add(inv)
    await session.flush()
    return inv, payment


@pytest.mark.asyncio
async def test_confirm_invoice_reduces_balance(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import confirm_invoice_payment

    env = ov_env
    arr = await _ov_arr(session, env, status=ArrangementStatus.Active)
    inv, payment = await _invoice_with_payment(session, env, arr, amount=100.0, inv_status=InvoiceStatus.Pending)
    await session.commit()

    result_arr, notif = await confirm_invoice_payment(session, payment, admin_user_id=1)
    await session.commit()

    await session.refresh(inv)
    await session.refresh(payment)
    assert inv.status == InvoiceStatus.Paid
    assert inv.paid_at is not None
    assert payment.status == FeePaymentStatus.Confirmed
    assert result_arr.balance == 0.0
    assert result_arr.status == ArrangementStatus.Active
    assert notif is None  # was already active, no reactivation


@pytest.mark.asyncio
async def test_confirm_invoice_reactivates_suspended(session: AsyncSession, ov_env: _Env) -> None:
    from app.models.notification import NotificationType
    from app.services.fee_order_value import confirm_invoice_payment

    env = ov_env
    arr = await _ov_arr(session, env, status=ArrangementStatus.Suspended)
    inv, payment = await _invoice_with_payment(session, env, arr, amount=100.0, inv_status=InvoiceStatus.Overdue)
    await session.commit()

    result_arr, notif = await confirm_invoice_payment(session, payment, admin_user_id=1)
    await session.commit()

    assert result_arr.status == ArrangementStatus.Active
    assert notif == NotificationType.FeeReactivated


@pytest.mark.asyncio
async def test_confirm_invoice_stays_suspended_with_other_unpaid(
    session: AsyncSession, ov_env: _Env
) -> None:
    from app.services.fee_order_value import confirm_invoice_payment

    env = ov_env
    arr = await _ov_arr(session, env, status=ArrangementStatus.Suspended)
    inv1, pay1 = await _invoice_with_payment(
        session, env, arr, amount=100.0, inv_status=InvoiceStatus.Overdue,
    )
    # a second, still-unpaid invoice (different period so the unique constraint holds)
    inv2 = FeeInvoice(
        arrangement_id=arr.id, store_id=env.store.id, service_id=env.service_id,
        period_start=date(2026, 2, 1), period_end=date(2026, 2, 28),
        sales_total=5000.0, fee_percent_snapshot=2.0, amount_due=100.0,
        status=InvoiceStatus.Overdue, issued_on=date(2026, 3, 5),
        due_date=date(2026, 3, 12), suspend_after=date(2026, 3, 14),
    )
    session.add(inv2)
    arr.balance += 100.0
    session.add(arr)
    await session.commit()

    result_arr, notif = await confirm_invoice_payment(session, pay1, admin_user_id=1)
    await session.commit()

    assert result_arr.status == ArrangementStatus.Suspended  # inv2 still unpaid
    assert notif is None
