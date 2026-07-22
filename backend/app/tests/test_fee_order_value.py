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
    suspended_reason: str | None = None,
) -> FeeArrangement:
    arr = FeeArrangement(
        store_id=env.store.id,
        service_id=env.service_id,
        model=FeeModel.OrderValuePercent,
        status=status,
        security_deposit_amount=deposit,
        order_value_activated_on=activated_on,
        last_billed_period_end=last_billed_period_end,
        suspended_reason=suspended_reason,
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

    created = await generate_order_value_invoices(session, date(2026, 2, 4))  # before the 5th
    await session.commit()
    assert created == 0
    assert len(await _invoices(session, arr.id)) == 0


@pytest.mark.asyncio
async def test_generate_invoice_catches_up_missed_day(session: AsyncSession, ov_env: _Env) -> None:
    """A sweep that runs AFTER the billing day still bills the prior month."""
    from app.services.fee_order_value import generate_order_value_invoices

    env = ov_env
    await _ov_cfg(session, env.service_id, percent=2.0, billing_day=5)
    arr = await _ov_arr(session, env, activated_on=date(2026, 1, 1))
    await _ov_order(session, env, total=1000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 15)))
    await session.commit()

    # Feb 5 sweep was missed; the Feb 8 run still generates January's invoice.
    created = await generate_order_value_invoices(session, date(2026, 2, 8))
    await session.commit()

    invs = await _invoices(session, arr.id)
    assert created == 1 and len(invs) == 1
    assert invs[0].period_start == date(2026, 1, 1)
    assert invs[0].period_end == date(2026, 1, 31)
    assert invs[0].amount_due == 20.0


@pytest.mark.asyncio
async def test_generate_invoice_catches_up_missed_month(session: AsyncSession, ov_env: _Env) -> None:
    """A whole missed month is caught up: two invoices (Jan + Feb) on one run."""
    from app.services.fee_order_value import generate_order_value_invoices

    env = ov_env
    await _ov_cfg(session, env.service_id, percent=2.0, billing_day=5)
    arr = await _ov_arr(session, env, activated_on=date(2026, 1, 1))
    await _ov_order(session, env, total=1000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 15)))
    await _ov_order(session, env, total=2000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 2, 15)))
    await session.commit()

    # Neither Feb 5 nor... the first run happens Mar 5 → bills BOTH Jan and Feb.
    created = await generate_order_value_invoices(session, date(2026, 3, 5))
    await session.commit()

    invs = sorted(await _invoices(session, arr.id), key=lambda i: i.period_start)
    assert created == 2 and len(invs) == 2
    assert invs[0].period_start == date(2026, 1, 1) and invs[0].amount_due == 20.0
    assert invs[1].period_start == date(2026, 2, 1) and invs[1].amount_due == 40.0
    await session.refresh(arr)
    assert arr.balance == 60.0
    assert arr.last_billed_period_end == date(2026, 2, 28)


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
    from app.services.fee_order_value import NONPAYMENT_REASON, confirm_invoice_payment

    env = ov_env
    arr = await _ov_arr(
        session, env, status=ArrangementStatus.Suspended, suspended_reason=NONPAYMENT_REASON,
    )
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
    from app.services.fee_order_value import NONPAYMENT_REASON, confirm_invoice_payment

    env = ov_env
    arr = await _ov_arr(
        session, env, status=ArrangementStatus.Suspended, suspended_reason=NONPAYMENT_REASON,
    )
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


@pytest.mark.asyncio
async def test_confirm_invoice_does_not_resurrect_terminated(
    session: AsyncSession, ov_env: _Env
) -> None:
    """Paying the trailing invoice of an admin-TERMINATED arrangement must not
    reactivate it (only non-payment suspensions auto-reactivate)."""
    from app.services.fee_order_value import confirm_invoice_payment

    env = ov_env
    arr = await _ov_arr(
        session, env, status=ArrangementStatus.Suspended,
        suspended_reason="admin_terminate",  # NOT the non-payment reason
    )
    inv, payment = await _invoice_with_payment(
        session, env, arr, amount=100.0, inv_status=InvoiceStatus.Pending,
    )
    await session.commit()

    result_arr, notif = await confirm_invoice_payment(session, payment, admin_user_id=1)
    await session.commit()

    await session.refresh(inv)
    assert inv.status == InvoiceStatus.Paid  # bill still settles
    assert result_arr.status == ArrangementStatus.Suspended  # stays terminated
    assert notif is None


@pytest.mark.asyncio
async def test_api_invoice_pay_confirm_loop(
    client, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    from app import app
    from app.core.security import get_current_seller

    bundle = approved_seller_with_store
    sid = bundle.service_id
    await _persist_test_admin(session)
    await _ov_cfg(session, sid, percent=2.0)
    arr = FeeArrangement(
        store_id=bundle.store.id, service_id=sid,
        model=FeeModel.OrderValuePercent, status=ArrangementStatus.Active,
        security_deposit_amount=500.0,
    )
    session.add(arr)
    await session.flush()
    inv = FeeInvoice(
        arrangement_id=arr.id, store_id=bundle.store.id, service_id=sid,
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
        sales_total=5000.0, fee_percent_snapshot=2.0, amount_due=100.0,
        status=InvoiceStatus.Pending, issued_on=date(2026, 2, 5),
        due_date=date(2026, 2, 12), suspend_after=date(2026, 2, 14),
    )
    session.add(inv)
    arr.balance = 100.0
    session.add(arr)
    await session.commit()
    arr_id, inv_id = arr.id, inv.id

    app.dependency_overrides[get_current_seller] = lambda: bundle.user
    try:
        r = await client.get(f"/api/v1/sellers/me/plan/{sid}/invoices")
        assert r.status_code == 200, r.text
        assert len(r.json()) == 1 and r.json()[0]["status"] == "pending"

        r2 = await client.post(
            f"/api/v1/sellers/me/plan/{sid}/invoices/{inv_id}/mark-paid"
        )
        assert r2.status_code == 200, r2.text
        payment_id = r2.json()["payment_id"]
    finally:
        app.dependency_overrides.pop(get_current_seller, None)

    r3 = await client.post(
        f"/api/v1/admin/fees/payments/{payment_id}/confirm", headers=admin_auth_headers
    )
    assert r3.status_code == 200, r3.text

    await session.refresh(inv)
    assert inv.status == InvoiceStatus.Paid

    r4 = await client.get(
        f"/api/v1/admin/fees/arrangements/{arr_id}/invoices", headers=admin_auth_headers
    )
    assert r4.status_code == 200, r4.text
    assert r4.json()[0]["status"] == "paid"


# ─── Slice E: forfeit, refund, switch-out ────────────────────────────────


async def _mk_period_invoice(
    session: AsyncSession, env: _Env, arr: FeeArrangement, *,
    amount: float, period_start: date, period_end: date,
    status: InvoiceStatus = InvoiceStatus.Overdue,
) -> FeeInvoice:
    inv = FeeInvoice(
        arrangement_id=arr.id, store_id=env.store.id, service_id=env.service_id,
        period_start=period_start, period_end=period_end, sales_total=amount * 50,
        fee_percent_snapshot=2.0, amount_due=amount, status=status,
        issued_on=period_end, due_date=period_end, suspend_after=period_end,
    )
    session.add(inv)
    arr.balance = round(arr.balance + amount, 2)
    session.add(arr)
    await session.flush()
    return inv


@pytest.mark.asyncio
async def test_forfeit_waives_invoice_and_reactivates(session: AsyncSession, ov_env: _Env) -> None:
    from app.models.notification import NotificationType
    from app.services.fee_order_value import NONPAYMENT_REASON, forfeit_deposit

    env = ov_env
    arr = await _ov_arr(
        session, env, status=ArrangementStatus.Suspended, deposit=500.0,
        suspended_reason=NONPAYMENT_REASON,
    )
    inv = await _mk_invoice(
        session, env, arr, amount=100.0, status=InvoiceStatus.Overdue,
        due_date=date(2026, 2, 12), suspend_after=date(2026, 2, 14),
    )
    await session.commit()

    result_arr, notif = await forfeit_deposit(
        session, arr, 100.0, admin_user_id=1, reason="nonpayment write-down"
    )
    await session.commit()

    await session.refresh(arr)
    await session.refresh(inv)
    assert arr.security_deposit_amount == 400.0
    assert arr.balance == 0.0
    assert inv.status == InvoiceStatus.Waived  # settled by the forfeit — not re-payable
    assert arr.status == ArrangementStatus.Active  # cleared last unpaid → reactivated
    assert notif == NotificationType.FeeReactivated


@pytest.mark.asyncio
async def test_forfeit_over_deposit_raises(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_lifecycle import FeeError
    from app.services.fee_order_value import forfeit_deposit

    env = ov_env
    arr = await _ov_arr(session, env, deposit=500.0)
    await session.commit()
    with pytest.raises(FeeError, match="bad_forfeit_amount"):
        await forfeit_deposit(session, arr, 600.0, admin_user_id=1)
    with pytest.raises(FeeError, match="bad_forfeit_amount"):
        await forfeit_deposit(session, arr, 0.0, admin_user_id=1)


@pytest.mark.asyncio
async def test_forfeit_settles_whole_invoices_only(session: AsyncSession, ov_env: _Env) -> None:
    """Forfeit waives whole invoices oldest-first; an amount that can't cover a
    whole invoice leaves it owed, and balance stays == sum(unpaid invoices)."""
    from app.services.fee_order_value import NONPAYMENT_REASON, forfeit_deposit

    env = ov_env
    arr = await _ov_arr(
        session, env, status=ArrangementStatus.Suspended, deposit=50.0,
        suspended_reason=NONPAYMENT_REASON,
    )
    inv_jan = await _mk_period_invoice(session, env, arr, amount=50.0, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31))
    inv_feb = await _mk_period_invoice(session, env, arr, amount=150.0, period_start=date(2026, 2, 1), period_end=date(2026, 2, 28))
    await session.commit()

    result_arr, notif = await forfeit_deposit(session, arr, 50.0, admin_user_id=1)
    await session.commit()

    await session.refresh(arr)
    await session.refresh(inv_jan)
    await session.refresh(inv_feb)
    assert arr.security_deposit_amount == 0.0
    assert inv_jan.status == InvoiceStatus.Waived  # 50 covered
    assert inv_feb.status == InvoiceStatus.Overdue  # 150 not covered by 50
    assert arr.balance == 150.0  # shortfall stays owed, balance == unpaid invoices
    assert arr.status == ArrangementStatus.Suspended  # still unpaid → not reactivated
    assert notif is None


@pytest.mark.asyncio
async def test_refund_requires_exit_state(session: AsyncSession, ov_env: _Env) -> None:
    """Refund is rejected on a live (Active) arrangement — never strips collateral."""
    from app.services.fee_lifecycle import FeeError
    from app.services.fee_order_value import refund_deposit

    env = ov_env
    arr = await _ov_arr(session, env, status=ArrangementStatus.Active, deposit=500.0)
    await session.commit()
    with pytest.raises(FeeError, match="refund_requires_exit"):
        await refund_deposit(session, arr, "offline", admin_user_id=1)


@pytest.mark.asyncio
async def test_refund_offline_records_negative_payment(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import refund_deposit

    env = ov_env
    arr = await _ov_arr(
        session, env, status=ArrangementStatus.Suspended, deposit=500.0,
        suspended_reason="admin_terminate",
    )
    inv = await _mk_invoice(
        session, env, arr, amount=100.0, status=InvoiceStatus.Overdue,
        due_date=date(2026, 2, 12), suspend_after=date(2026, 2, 14),
    )
    await session.commit()

    refunded = await refund_deposit(session, arr, "offline", admin_user_id=1)
    await session.commit()

    assert refunded == 400.0
    await session.refresh(arr)
    await session.refresh(inv)
    assert arr.security_deposit_amount == 0.0
    assert arr.balance == 0.0
    assert inv.status == InvoiceStatus.Cancelled  # trailing invoice written off
    pay = (
        await session.exec(
            select(FeePayment).where(
                FeePayment.arrangement_id == arr.id,
                FeePayment.kind == FeePaymentKind.SecurityDeposit,
            )
        )
    ).first()
    assert pay is not None and pay.amount == -400.0
    assert pay.status == FeePaymentStatus.Confirmed


@pytest.mark.asyncio
async def test_refund_credit_grants_wallet(session: AsyncSession, ov_env: _Env) -> None:
    from app.services import store_credit
    from app.services.fee_order_value import refund_deposit

    env = ov_env
    arr = await _ov_arr(
        session, env, status=ArrangementStatus.Suspended, deposit=500.0,
        suspended_reason="admin_terminate",
    )  # balance 0
    await session.commit()

    refunded = await refund_deposit(session, arr, "credit", admin_user_id=1)
    await session.commit()

    assert refunded == 500.0
    store = await store_credit.load_store(session, env.store.id)
    assert store.fee_credit_balance == 500.0


@pytest.mark.asyncio
async def test_refund_when_outstanding_exceeds_deposit(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import refund_deposit

    env = ov_env
    arr = await _ov_arr(
        session, env, status=ArrangementStatus.Suspended, deposit=50.0,
        suspended_reason="admin_terminate",
    )
    await _mk_invoice(
        session, env, arr, amount=200.0, status=InvoiceStatus.Overdue,
        due_date=date(2026, 2, 12), suspend_after=date(2026, 2, 14),
    )
    await session.commit()

    refunded = await refund_deposit(session, arr, "offline", admin_user_id=1)
    await session.commit()

    assert refunded == 0.0
    await session.refresh(arr)
    assert arr.security_deposit_amount == 0.0
    assert arr.balance == 0.0  # deposit consumed; remainder written off (invoice Cancelled)


@pytest.mark.asyncio
async def test_final_invoice_bills_trailing_sales(session: AsyncSession, ov_env: _Env) -> None:
    from app.services.fee_order_value import generate_final_order_value_invoice

    env = ov_env
    await _ov_cfg(session, env.service_id, percent=2.0)
    arr = await _ov_arr(session, env, activated_on=date(2026, 1, 1))
    await _ov_order(session, env, total=1000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 15)))
    await _ov_order(session, env, total=500.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 2, 2)))
    await session.commit()

    inv = await generate_final_order_value_invoice(session, arr, date(2026, 2, 10))
    await session.commit()

    assert inv is not None
    assert inv.period_start == date(2026, 1, 1)
    assert inv.period_end == date(2026, 2, 10)
    assert inv.sales_total == 1500.0
    assert inv.amount_due == 30.0
    await session.refresh(arr)
    assert arr.balance == 30.0
    assert arr.last_billed_period_end == date(2026, 2, 10)


@pytest.mark.asyncio
async def test_api_admin_forfeit_then_refund_exit(
    client, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    """Exit settlement: a terminated (Suspended) arrangement — admin forfeits
    part of the deposit against the outstanding invoice (does NOT resurrect the
    terminated store), then refunds the remainder."""
    bundle = approved_seller_with_store
    sid = bundle.service_id
    await _persist_test_admin(session)
    await _ov_cfg(session, sid, percent=2.0)
    arr = FeeArrangement(
        store_id=bundle.store.id, service_id=sid,
        model=FeeModel.OrderValuePercent, status=ArrangementStatus.Suspended,
        security_deposit_amount=500.0, suspended_reason="admin_terminate",
    )
    session.add(arr)
    await session.flush()
    inv = FeeInvoice(
        arrangement_id=arr.id, store_id=bundle.store.id, service_id=sid,
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
        sales_total=5000.0, fee_percent_snapshot=2.0, amount_due=100.0,
        status=InvoiceStatus.Overdue, issued_on=date(2026, 2, 5),
        due_date=date(2026, 2, 12), suspend_after=date(2026, 2, 14),
    )
    session.add(inv)
    arr.balance = 100.0
    session.add(arr)
    await session.commit()
    arr_id, inv_id = arr.id, inv.id

    r = await client.post(
        f"/api/v1/admin/fees/arrangements/{arr_id}/forfeit",
        headers=admin_auth_headers,
        json={"amount": 100.0, "invoice_id": inv_id, "reason": "exit write-down over 10 chars"},
    )
    assert r.status_code == 200, r.text
    await session.refresh(arr)
    await session.refresh(inv)
    assert arr.security_deposit_amount == 400.0
    assert arr.balance == 0.0
    assert inv.status == InvoiceStatus.Waived
    assert arr.status == ArrangementStatus.Suspended  # terminated store NOT resurrected

    r2 = await client.post(
        f"/api/v1/admin/fees/arrangements/{arr_id}/refund-deposit",
        headers=admin_auth_headers,
        json={"mode": "credit", "note": "exit settlement"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["refunded"] == 400.0
    await session.refresh(arr)
    assert arr.security_deposit_amount == 0.0


@pytest.mark.asyncio
async def test_api_admin_terminate_bills_final_invoice(
    client, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    bundle = approved_seller_with_store
    sid = bundle.service_id
    await _persist_test_admin(session)
    await _ov_cfg(session, sid, percent=2.0)
    arr = FeeArrangement(
        store_id=bundle.store.id, service_id=sid,
        model=FeeModel.OrderValuePercent, status=ArrangementStatus.Active,
        security_deposit_amount=500.0, order_value_activated_on=date(2026, 1, 1),
    )
    session.add(arr)
    await session.flush()
    # a trailing delivered order not yet billed
    user = User(email=f"c2-{uuid.uuid4().hex[:8]}@x.test", role=UserRole.Customer)
    session.add(user)
    await session.flush()
    prof = CustomerProfile(user_id=user.id, first_name="C2")
    session.add(prof)
    addr = Address(**make_address())
    session.add(addr)
    await session.flush()
    order = Order(
        customer_profile_id=prof.id, store_id=bundle.store.id, service_id=sid,
        service_name_snapshot="Grocery", delivery_address_id=addr.id,
        status=OrderStatus.Delivered, subtotal=1000.0, delivery_fee=0.0, tax=0.0,
        total=1000.0, delivery_address_snapshot="addr", placed_at=_at(date(2026, 1, 15)),
    )
    session.add(order)
    await session.commit()
    arr_id = arr.id

    r = await client.post(
        f"/api/v1/admin/fees/arrangements/{arr_id}/terminate",
        headers=admin_auth_headers,
        json={"reason": "seller exiting order-value plan"},
    )
    assert r.status_code == 200, r.text

    await session.refresh(arr)
    assert arr.status == ArrangementStatus.Suspended
    invs = await _invoices(session, arr_id)
    assert len(invs) == 1
    assert invs[0].amount_due == 20.0  # 1000 * 2%


@pytest.mark.asyncio
async def test_switch_out_settles_deposit_not_wiped(session: AsyncSession, ov_env: _Env) -> None:
    """Switching OV → Freebie bills trailing sales + settles the deposit to
    wallet credit; it must NOT silently zero the balance or orphan the deposit."""
    from app.services import store_credit
    from app.services.fee_lifecycle import admin_switch_model

    env = ov_env
    await _ov_cfg(session, env.service_id, percent=2.0)
    arr = await _ov_arr(
        session, env, status=ArrangementStatus.Active, deposit=500.0,
        activated_on=date(2026, 1, 1), last_billed_period_end=date(2026, 1, 31),
    )
    # Trailing Feb sales, not yet billed.
    await _ov_order(session, env, total=2000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 2, 15)))
    await session.commit()

    await admin_switch_model(
        session, arr, target_model=FeeModel.Freebie, disposition="credit",
        admin_user_id=1, today=date(2026, 3, 10),
    )
    await session.commit()

    await session.refresh(arr)
    assert arr.model == FeeModel.Freebie
    assert arr.balance == 0.0
    assert arr.security_deposit_amount == 0.0
    store = await store_credit.load_store(session, env.store.id)
    # Feb fee = 2000 * 2% = 40 consumed from the 500 deposit → 460 returned.
    assert store.fee_credit_balance == 460.0


@pytest.mark.asyncio
async def test_api_config_exposes_payment_days(
    client, session: AsyncSession, approved_seller_with_store, admin_auth_headers
) -> None:
    bundle = approved_seller_with_store
    sid = bundle.service_id
    await _persist_test_admin(session)

    r = await client.patch(
        f"/api/v1/admin/fees/services/{sid}",
        headers=admin_auth_headers,
        json={"order_value_enabled": True, "order_value_payment_days": 10},
    )
    assert r.status_code == 200, r.text
    assert r.json()["order_value_payment_days"] == 10

    r2 = await client.get(
        f"/api/v1/admin/fees/services/{sid}", headers=admin_auth_headers
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["config"]["order_value_payment_days"] == 10


# ─── Slice F: notifications ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invoice_records_inapp_notification(
    session: AsyncSession, approved_seller_with_store, ov_env: _Env
) -> None:
    from app.models.notification import Notification
    from app.services.fee_order_value import generate_order_value_invoices

    env = ov_env
    await _ov_cfg(session, env.service_id, percent=2.0, billing_day=5)
    await _ov_arr(session, env, activated_on=date(2026, 1, 1))
    await _ov_order(session, env, total=1000.0, status=OrderStatus.Delivered, placed_at=_at(date(2026, 1, 15)))
    await session.commit()

    await generate_order_value_invoices(session, date(2026, 2, 5))
    await session.commit()

    notes = (
        await session.exec(
            select(Notification).where(
                Notification.seller_profile_id == approved_seller_with_store.profile.id,
                Notification.type == NotificationType.FeeInvoiceRaised,
            )
        )
    ).all()
    assert len(notes) == 1


def test_fee_channel_copy_has_invoice_types() -> None:
    from app.worker import _FEE_CHANNEL_COPY

    assert "fee_invoice_raised" in _FEE_CHANNEL_COPY
    assert "fee_invoice_overdue" in _FEE_CHANNEL_COPY
