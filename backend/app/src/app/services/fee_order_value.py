# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Order Value % (postpaid + security deposit) fee model.

Monthly postpaid billing: on the configured billing day, a FeeInvoice is raised
for the prior calendar month's completed (delivered) sales, charged at the
service's `order_value_percent`. Non-payment (after the payment window + grace)
suspends the arrangement; paying + admin-confirm auto-reactivates. A held
security deposit is collateral, forfeited/refunded only by explicit admin action.

Cycle boundaries are computed in IST (Asia/Kolkata); `Order.placed_at` is
timezone-aware UTC, so period bounds are converted to UTC for the sales query.

Service functions FLUSH; the caller COMMITS (mirrors fee_lifecycle)."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func as safunc
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Order, OrderStatus
from app.models.notification import NotificationType
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeEvent,
    FeeEventType,
    FeeInvoice,
    FeeModel,
    FeePayment,
    FeePaymentKind,
    FeePaymentStatus,
    InvoiceStatus,
    PlatformFeeSettings,
    ServiceFeeConfig,
)
from app.services.fee_lifecycle import FeeError
from app.services.fee_notifications import notify_seller_fee_event

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_GRACE_DAYS = 2


def _last_day_of_month(d: date) -> int:
    """Last calendar day of the month containing `d`."""
    nxt = d.replace(day=28) + timedelta(days=4)
    return (nxt.replace(day=1) - timedelta(days=1)).day


async def compute_order_value_sales(
    session: AsyncSession,
    store_id: int,
    service_id: int,
    period_start: date,
    period_end: date,
) -> float:
    """Sum the grand total (`Order.total`) of DELIVERED orders for a
    (store, service) whose `placed_at` falls within [period_start, period_end]
    (inclusive), interpreting the date bounds in IST."""
    start_utc = datetime.combine(period_start, time.min, tzinfo=IST)
    end_utc = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=IST)
    total = (
        await session.exec(
            select(safunc.coalesce(safunc.sum(Order.total), 0.0)).where(
                Order.store_id == store_id,
                Order.service_id == service_id,
                Order.status == OrderStatus.Delivered,
                Order.placed_at >= start_utc,
                Order.placed_at < end_utc,
            )
        )
    ).one()
    return float(total or 0.0)


async def _grace_days(session: AsyncSession) -> int:
    settings = (
        await session.exec(
            select(PlatformFeeSettings).order_by(PlatformFeeSettings.id).limit(1)  # type: ignore[arg-type]
        )
    ).first()
    return settings.grace_period_days if settings else DEFAULT_GRACE_DAYS


async def generate_order_value_invoices(
    session: AsyncSession,
    today: date,
    *,
    notices: list[tuple[int, str, "date | None"]] | None = None,
) -> int:
    """On each arrangement's billing day, raise a FeeInvoice for the prior
    calendar month's completed sales. Idempotent (unique arrangement+period).
    A zero-amount invoice is auto-settled (Paid). Flushes; caller commits.
    Returns the number of invoices created."""
    prev_end = today.replace(day=1) - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    grace = await _grace_days(session)
    created = 0

    arrangements = (
        await session.exec(
            select(FeeArrangement).where(
                FeeArrangement.model == FeeModel.OrderValuePercent,
                FeeArrangement.status.in_(  # type: ignore[attr-defined]
                    [ArrangementStatus.Active, ArrangementStatus.Grace]
                ),
            )
        )
    ).all()

    for arr in arrangements:
        cfg = (
            await session.exec(
                select(ServiceFeeConfig).where(
                    ServiceFeeConfig.service_id == arr.service_id
                )
            )
        ).first()
        if cfg is None:
            continue
        billing_day = min(cfg.order_value_billing_day, _last_day_of_month(today))
        if today.day != billing_day:
            continue

        period_start = prev_start
        if arr.order_value_activated_on and arr.order_value_activated_on > period_start:
            period_start = arr.order_value_activated_on
        if arr.last_billed_period_end and arr.last_billed_period_end >= period_start:
            period_start = arr.last_billed_period_end + timedelta(days=1)
        if period_start > prev_end:
            continue  # activated after the period closed; bill next cycle

        already = (
            await session.exec(
                select(FeeInvoice).where(
                    FeeInvoice.arrangement_id == arr.id,
                    FeeInvoice.period_start == period_start,
                )
            )
        ).first()
        if already is not None:
            continue

        sales = await compute_order_value_sales(
            session, arr.store_id, arr.service_id, period_start, prev_end
        )
        pct = cfg.order_value_percent
        amount = round(sales * pct / 100.0, 2)
        due = today + timedelta(days=cfg.order_value_payment_days)
        is_zero = amount <= 0.0

        invoice = FeeInvoice(
            arrangement_id=arr.id,
            store_id=arr.store_id,
            service_id=arr.service_id,
            period_start=period_start,
            period_end=prev_end,
            sales_total=sales,
            fee_percent_snapshot=pct,
            amount_due=amount,
            status=InvoiceStatus.Paid if is_zero else InvoiceStatus.Pending,
            issued_on=today,
            due_date=due,
            suspend_after=due + timedelta(days=grace),
            paid_at=datetime.now(timezone.utc) if is_zero else None,
        )
        session.add(invoice)
        if not is_zero:
            arr.balance += amount
        arr.last_billed_period_end = prev_end
        session.add(arr)
        session.add(
            FeeEvent(
                arrangement_id=arr.id,
                event_type=FeeEventType.InvoiceIssued,
                amount_delta=amount,
                actor="system",
                note=f"invoice {period_start}..{prev_end} sales={sales}",
            )
        )
        if not is_zero and notices is not None:
            notices.append((arr.store_id, "FeeInvoiceRaised", None))
        created += 1

    await session.flush()
    return created


async def _order_value_config(
    session: AsyncSession, service_id: int
) -> ServiceFeeConfig:
    """Return the service's fee config, or raise if Order Value % isn't offerable."""
    cfg = (
        await session.exec(
            select(ServiceFeeConfig).where(ServiceFeeConfig.service_id == service_id)
        )
    ).first()
    if cfg is None or not cfg.order_value_enabled:
        raise FeeError("order_value_not_offerable")
    return cfg


async def opt_into_order_value(
    session: AsyncSession,
    arrangement: FeeArrangement,
    deposit_amount: float,
    *,
    now: datetime | None = None,
) -> FeePayment:
    """Seller opts into Order Value %: pay the min security deposit offline, admin
    confirms it, then the arrangement activates (deposit-first). Creates a pending
    SecurityDeposit FeePayment; the arrangement flips to PendingActivation. Caller
    commits."""
    now = now or datetime.now(timezone.utc)
    cfg = await _order_value_config(session, arrangement.service_id)
    if deposit_amount < cfg.order_value_min_deposit:
        raise FeeError("below_min_deposit")
    existing_pending = (
        await session.exec(
            select(FeePayment).where(
                FeePayment.arrangement_id == arrangement.id,
                FeePayment.status == FeePaymentStatus.Pending,
            )
        )
    ).first()
    if existing_pending is not None:
        raise FeeError("payment_already_pending")

    arrangement.model = FeeModel.OrderValuePercent
    arrangement.status = ArrangementStatus.PendingActivation
    arrangement.pending_since = now
    session.add(arrangement)
    payment = FeePayment(
        arrangement_id=arrangement.id,
        kind=FeePaymentKind.SecurityDeposit,
        amount=deposit_amount,
        status=FeePaymentStatus.Pending,
    )
    session.add(payment)
    await session.flush()
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.PaymentRecorded,
            amount_delta=deposit_amount,
            actor="seller",
            note="order-value opt-in deposit",
        )
    )
    return payment


async def confirm_order_value_deposit(
    session: AsyncSession,
    payment: FeePayment,
    admin_user_id: int,
    *,
    today: date | None = None,
) -> tuple[FeeArrangement, NotificationType | None]:
    """Admin confirms the offline security deposit → arrangement goes Active and
    billing anchors are set. Records the single in-app FeeActivated notification;
    caller does channel fan-out. Returns (arrangement, notification_type). Caller
    commits."""
    today = today or date.today()
    arrangement = (
        await session.exec(
            select(FeeArrangement).where(FeeArrangement.id == payment.arrangement_id)
        )
    ).one()

    arrangement.model = FeeModel.OrderValuePercent
    arrangement.security_deposit_amount = payment.amount
    arrangement.status = ArrangementStatus.Active
    arrangement.order_value_activated_on = today
    arrangement.last_billed_period_end = None
    arrangement.pending_since = None
    arrangement.valid_until = None
    session.add(arrangement)

    payment.status = FeePaymentStatus.Confirmed
    payment.confirmed_by_admin_id = admin_user_id
    payment.confirmed_at = datetime.now(timezone.utc)
    session.add(payment)

    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.DepositRecorded,
            amount_delta=payment.amount,
            actor=f"admin:{admin_user_id}",
            note="order-value security deposit",
        )
    )
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.Activated,
            actor=f"admin:{admin_user_id}",
            note="order-value activated",
        )
    )
    await session.flush()

    notif = NotificationType.FeeActivated
    await notify_seller_fee_event(session, store_id=arrangement.store_id, type=notif)
    await session.flush()
    return arrangement, notif
