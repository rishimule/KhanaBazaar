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
    StoreCreditReason,
)
from app.services import store_credit
from app.services.fee_lifecycle import FeeError, _suspend
from app.services.fee_notifications import notify_seller_fee_event

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_GRACE_DAYS = 2
# Marks a suspension caused by an unpaid order-value invoice. Only suspensions
# with this reason auto-reactivate on payment/forfeit — an admin *terminate*
# (different reason, auto_renew=False) must never be resurrected by settling a bill.
NONPAYMENT_REASON = "order_value_nonpayment"


def _last_day_of_month(d: date) -> int:
    """Last calendar day of the month containing `d`."""
    nxt = d.replace(day=28) + timedelta(days=4)
    return (nxt.replace(day=1) - timedelta(days=1)).day


def _month_end(d: date) -> date:
    """Last date of the calendar month containing `d`."""
    return d.replace(day=_last_day_of_month(d))


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
    notices: list[tuple[int, str, str | None]] | None = None,
) -> int:
    """Raise FeeInvoices for every *complete, unbilled* calendar month that has
    become due (its month's invoice is due on the next month's billing day).
    Bills each month oldest-first, so a missed sweep day (or a whole missed
    month) is caught up on the next run — never silently skipped. Idempotent
    (unique arrangement+period). A zero-amount invoice is auto-settled (Paid).
    Flushes; caller commits. Returns the number of invoices created."""
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

    this_month_start = today.replace(day=1)
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
        # The prior month becomes billable once we reach the billing day this
        # month; before that, only months ending before the prior month are due.
        if today.day >= billing_day:
            last_billable_end = this_month_start - timedelta(days=1)
        else:
            prior_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
            last_billable_end = prior_month_start - timedelta(days=1)

        # Earliest unbilled period start: after the last billed month, else from
        # activation (which may be mid-month → partial first invoice).
        if arr.last_billed_period_end is not None:
            cursor = arr.last_billed_period_end + timedelta(days=1)
        elif arr.order_value_activated_on is not None:
            cursor = arr.order_value_activated_on
        else:
            continue

        while cursor <= last_billable_end:
            period_end = _month_end(cursor)
            already = (
                await session.exec(
                    select(FeeInvoice).where(
                        FeeInvoice.arrangement_id == arr.id,
                        FeeInvoice.period_start == cursor,
                    )
                )
            ).first()
            if already is None:
                if await _emit_invoice(
                    session, arr, cfg, cursor, period_end,
                    issued_on=today, grace=grace, notices=notices,
                ):
                    created += 1
            arr.last_billed_period_end = period_end
            session.add(arr)
            cursor = period_end + timedelta(days=1)

    await session.flush()
    return created


async def _emit_invoice(
    session: AsyncSession,
    arr: FeeArrangement,
    cfg: ServiceFeeConfig,
    period_start: date,
    period_end: date,
    *,
    issued_on: date,
    grace: int,
    notices: list[tuple[int, str, str | None]] | None,
) -> bool:
    """Create one FeeInvoice for [period_start, period_end], update balance +
    audit + notification. Zero-amount → auto-Paid. Returns True. Flush-only."""
    sales = await compute_order_value_sales(
        session, arr.store_id, arr.service_id, period_start, period_end
    )
    pct = cfg.order_value_percent
    amount = round(sales * pct / 100.0, 2)
    due = issued_on + timedelta(days=cfg.order_value_payment_days)
    is_zero = amount <= 0.0

    session.add(
        FeeInvoice(
            arrangement_id=arr.id,
            store_id=arr.store_id,
            service_id=arr.service_id,
            period_start=period_start,
            period_end=period_end,
            sales_total=sales,
            fee_percent_snapshot=pct,
            amount_due=amount,
            status=InvoiceStatus.Paid if is_zero else InvoiceStatus.Pending,
            issued_on=issued_on,
            due_date=due,
            suspend_after=due + timedelta(days=grace),
            paid_at=datetime.now(timezone.utc) if is_zero else None,
        )
    )
    if not is_zero:
        arr.balance = round(arr.balance + amount, 2)
    session.add(arr)
    session.add(
        FeeEvent(
            arrangement_id=arr.id,
            event_type=FeeEventType.InvoiceIssued,
            amount_delta=amount,
            actor="system",
            note=f"invoice {period_start}..{period_end} sales={sales}",
        )
    )
    if not is_zero:
        spid = await notify_seller_fee_event(
            session,
            store_id=arr.store_id,
            type=NotificationType.FeeInvoiceRaised,
            valid_until=due,
        )
        if notices is not None and spid is not None:
            notices.append(
                (spid, NotificationType.FeeInvoiceRaised.value, due.isoformat())
            )
    return True


async def generate_final_order_value_invoice(
    session: AsyncSession,
    arrangement: FeeArrangement,
    today: date,
) -> FeeInvoice | None:
    """On exit/switch-out, bill any completed sales since the last billed period
    (or activation) through `today` as a final partial invoice. Returns the
    invoice, or None if there's nothing to bill. Caller commits."""
    if arrangement.model != FeeModel.OrderValuePercent:
        return None
    cfg = (
        await session.exec(
            select(ServiceFeeConfig).where(
                ServiceFeeConfig.service_id == arrangement.service_id
            )
        )
    ).first()
    if cfg is None:
        return None

    start = arrangement.order_value_activated_on
    if arrangement.last_billed_period_end is not None:
        cand = arrangement.last_billed_period_end + timedelta(days=1)
        if start is None or cand > start:
            start = cand
    if start is None or start > today:
        return None

    exists = (
        await session.exec(
            select(FeeInvoice).where(
                FeeInvoice.arrangement_id == arrangement.id,
                FeeInvoice.period_start == start,
            )
        )
    ).first()
    if exists is not None:
        return None

    sales = await compute_order_value_sales(
        session, arrangement.store_id, arrangement.service_id, start, today
    )
    pct = cfg.order_value_percent
    amount = round(sales * pct / 100.0, 2)
    grace = await _grace_days(session)
    due = today + timedelta(days=cfg.order_value_payment_days)
    is_zero = amount <= 0.0

    invoice = FeeInvoice(
        arrangement_id=arrangement.id,
        store_id=arrangement.store_id,
        service_id=arrangement.service_id,
        period_start=start,
        period_end=today,
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
        arrangement.balance = round(arrangement.balance + amount, 2)
    arrangement.last_billed_period_end = today
    session.add(arrangement)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.InvoiceIssued,
            amount_delta=amount,
            actor="system",
            note=f"final invoice {start}..{today} sales={sales}",
        )
    )
    await session.flush()
    return invoice


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


async def sweep_order_value_overdue(
    session: AsyncSession,
    today: date,
    *,
    notices: list[tuple[int, str, str | None]] | None = None,
) -> dict[str, int]:
    """Daily overdue pass for Order Value % arrangements: pending invoices past
    their due date become Overdue (with a reminder); an arrangement with any
    unpaid invoice past its suspend_after date is suspended. Flushes; caller
    commits."""
    counts = {"overdue": 0, "suspended": 0}
    unpaid = (
        await session.exec(
            select(FeeInvoice).where(
                FeeInvoice.status.in_(  # type: ignore[attr-defined]
                    [InvoiceStatus.Pending, InvoiceStatus.Overdue]
                )
            )
        )
    ).all()

    to_suspend: set[int] = set()
    for inv in unpaid:
        if inv.status == InvoiceStatus.Pending and today > inv.due_date:
            inv.status = InvoiceStatus.Overdue
            session.add(inv)
            spid = await notify_seller_fee_event(
                session,
                store_id=inv.store_id,
                type=NotificationType.FeeInvoiceOverdue,
                valid_until=inv.suspend_after,
            )
            if notices is not None and spid is not None:
                notices.append(
                    (
                        spid,
                        NotificationType.FeeInvoiceOverdue.value,
                        inv.suspend_after.isoformat(),
                    )
                )
            counts["overdue"] += 1
        if today > inv.suspend_after:
            to_suspend.add(inv.arrangement_id)

    for arr_id in to_suspend:
        arr = await session.get(FeeArrangement, arr_id)
        if arr is None or arr.status not in (
            ArrangementStatus.Active,
            ArrangementStatus.Grace,
        ):
            continue
        _suspend(session, arr, NONPAYMENT_REASON)
        spid = await notify_seller_fee_event(
            session, store_id=arr.store_id, type=NotificationType.FeeSuspended
        )
        if notices is not None and spid is not None:
            notices.append((spid, NotificationType.FeeSuspended.value, None))
        counts["suspended"] += 1

    await session.flush()
    return counts


async def _unpaid_invoices(
    session: AsyncSession, arrangement_id: int
) -> list[FeeInvoice]:
    """Pending + Overdue invoices for an arrangement, oldest period first."""
    return list(
        (
            await session.exec(
                select(FeeInvoice)
                .where(
                    FeeInvoice.arrangement_id == arrangement_id,
                    FeeInvoice.status.in_(  # type: ignore[attr-defined]
                        [InvoiceStatus.Pending, InvoiceStatus.Overdue]
                    ),
                )
                .order_by(FeeInvoice.period_start)  # type: ignore[arg-type]
            )
        ).all()
    )


async def _reactivate_if_cleared(
    session: AsyncSession, arrangement: FeeArrangement, actor: str
) -> NotificationType | None:
    """If the arrangement is suspended FOR NON-PAYMENT and no unpaid invoices
    remain, flip it back to Active and record the FeeReactivated in-app
    notification. Returns the notification type (for channel fan-out) or None.
    Deliberately does NOT reactivate an admin-terminated arrangement."""
    if (
        arrangement.status != ArrangementStatus.Suspended
        or arrangement.suspended_reason != NONPAYMENT_REASON
    ):
        return None
    if await _unpaid_invoices(session, arrangement.id):  # type: ignore[arg-type]
        return None
    arrangement.status = ArrangementStatus.Active
    arrangement.suspended_at = None
    arrangement.suspended_reason = None
    session.add(arrangement)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.Reactivated,
            actor=actor,
            note="order-value outstanding cleared",
        )
    )
    await notify_seller_fee_event(
        session, store_id=arrangement.store_id, type=NotificationType.FeeReactivated
    )
    return NotificationType.FeeReactivated


async def settle_order_value_exit(
    session: AsyncSession,
    arrangement: FeeArrangement,
    today: date,
    *,
    disposition: str,
    admin_user_id: int,
) -> float:
    """Settle an Order Value % arrangement that is switching to another model.
    Bills trailing sales (final partial invoice), writes off any still-unpaid
    invoices, consumes the deposit against outstanding, and disposes the
    remainder per `disposition` ('credit' → wallet, 'cash_out' → offline record,
    'waive' → platform keeps it). Zeroes balance + deposit. Returns the amount
    returned to the seller. Caller commits. Prevents the silent balance-wipe /
    orphaned-deposit that a plain model switch would otherwise cause."""
    await generate_final_order_value_invoice(session, arrangement, today)
    for invoice in await _unpaid_invoices(session, arrangement.id):  # type: ignore[arg-type]
        invoice.status = InvoiceStatus.Cancelled
        session.add(invoice)

    deposit = arrangement.security_deposit_amount
    consumed = min(deposit, max(arrangement.balance, 0.0))
    returned = round(deposit - consumed, 2)
    arrangement.balance = 0.0
    arrangement.security_deposit_amount = 0.0
    session.add(arrangement)

    if returned > 0 and disposition != "waive":
        if disposition == "cash_out":
            session.add(
                FeePayment(
                    arrangement_id=arrangement.id,
                    kind=FeePaymentKind.SecurityDeposit,
                    amount=-returned,
                    status=FeePaymentStatus.Confirmed,
                    confirmed_by_admin_id=admin_user_id,
                    confirmed_at=datetime.now(timezone.utc),
                    seller_note="order-value switch-out refund",
                )
            )
        else:  # credit (default)
            store = await store_credit.load_store(session, arrangement.store_id)
            await store_credit.grant(
                session,
                store,
                returned,
                actor=f"admin:{admin_user_id}",
                note="order-value switch-out deposit",
                reason=StoreCreditReason.GrantedOnExit,
                related_arrangement_id=arrangement.id,
            )

    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.DepositRefunded,
            amount_delta=returned,
            actor=f"admin:{admin_user_id}",
            note=f"order-value switch-out settle ({disposition})",
        )
    )
    await session.flush()
    return returned


async def forfeit_deposit(
    session: AsyncSession,
    arrangement: FeeArrangement,
    amount: float,
    admin_user_id: int,
    *,
    invoice_id: int | None = None,
    reason: str | None = None,
) -> tuple[FeeArrangement, NotificationType | None]:
    """Admin forfeits `amount` of the held security deposit toward outstanding
    invoices. Never auto-triggered. To keep `balance` == sum(unpaid invoices),
    the forfeited amount settles WHOLE unpaid invoices (marking them Waived):
    the specific `invoice_id` if given, else oldest-first up to the applied
    amount. Reactivates the store if this clears the last non-payment invoice.
    Returns (arrangement, reactivation_notification|None). Caller commits."""
    # Row-lock to avoid a lost update racing another admin action / the sweep.
    arrangement = (
        await session.exec(
            select(FeeArrangement)
            .where(FeeArrangement.id == arrangement.id)
            .with_for_update()
        )
    ).one()
    if amount <= 0 or amount > arrangement.security_deposit_amount:
        raise FeeError("bad_forfeit_amount")

    arrangement.security_deposit_amount = round(
        arrangement.security_deposit_amount - amount, 2
    )

    waived_total = 0.0
    if invoice_id is not None:
        invoice = await session.get(FeeInvoice, invoice_id)
        if (
            invoice is not None
            and invoice.arrangement_id == arrangement.id
            and invoice.status in (InvoiceStatus.Pending, InvoiceStatus.Overdue)
        ):
            invoice.status = InvoiceStatus.Waived
            session.add(invoice)
            waived_total += invoice.amount_due
    else:
        remaining = amount
        for invoice in await _unpaid_invoices(session, arrangement.id):  # type: ignore[arg-type]
            if remaining + 1e-9 < invoice.amount_due:
                break
            invoice.status = InvoiceStatus.Waived
            session.add(invoice)
            remaining = round(remaining - invoice.amount_due, 2)
            waived_total += invoice.amount_due

    # balance mirrors the unpaid invoices, so drop exactly what we waived.
    arrangement.balance = round(arrangement.balance - waived_total, 2)
    session.add(arrangement)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.DepositForfeited,
            amount_delta=-amount,
            actor=f"admin:{admin_user_id}",
            note=reason or "deposit forfeited",
        )
    )
    notif = await _reactivate_if_cleared(session, arrangement, f"admin:{admin_user_id}")
    await session.flush()
    return arrangement, notif


async def refund_deposit(
    session: AsyncSession,
    arrangement: FeeArrangement,
    mode: str,
    admin_user_id: int,
    *,
    note: str | None = None,
) -> float:
    """Settle the held deposit on exit. Only valid once the arrangement is
    Suspended (exit state) — never strips collateral from a live store. Any
    remaining unpaid invoices are Cancelled (written off); the deposit first
    clears the outstanding, then the remainder (deposit - outstanding) is
    refunded via `mode`: 'offline' records a negative SecurityDeposit payment
    (money returned outside the platform); 'credit' grants store wallet credit.
    Zeroes the deposit + balance and returns the refunded amount. Caller commits."""
    if mode not in ("offline", "credit"):
        raise FeeError("bad_refund_mode")

    # Row-lock; guard against refunding a live (operating) store.
    arrangement = (
        await session.exec(
            select(FeeArrangement)
            .where(FeeArrangement.id == arrangement.id)
            .with_for_update()
        )
    ).one()
    if arrangement.status != ArrangementStatus.Suspended:
        raise FeeError("refund_requires_exit")

    deposit = arrangement.security_deposit_amount
    consumed = min(deposit, max(arrangement.balance, 0.0))
    refundable = round(deposit - consumed, 2)
    # Write off any still-unpaid invoices (the remainder beyond `consumed`).
    for invoice in await _unpaid_invoices(session, arrangement.id):  # type: ignore[arg-type]
        invoice.status = InvoiceStatus.Cancelled
        session.add(invoice)
    arrangement.balance = 0.0
    arrangement.security_deposit_amount = 0.0
    session.add(arrangement)

    if refundable > 0:
        if mode == "offline":
            session.add(
                FeePayment(
                    arrangement_id=arrangement.id,
                    kind=FeePaymentKind.SecurityDeposit,
                    amount=-refundable,
                    status=FeePaymentStatus.Confirmed,
                    confirmed_by_admin_id=admin_user_id,
                    confirmed_at=datetime.now(timezone.utc),
                    seller_note=note,
                )
            )
        else:  # credit
            store = await store_credit.load_store(session, arrangement.store_id)
            await store_credit.grant(
                session,
                store,
                refundable,
                actor=f"admin:{admin_user_id}",
                note=note or "order-value deposit refund",
                reason=StoreCreditReason.GrantedOnExit,
                related_arrangement_id=arrangement.id,
            )

    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.DepositRefunded,
            amount_delta=refundable,
            actor=f"admin:{admin_user_id}",
            note=note or f"deposit refund ({mode})",
        )
    )
    await session.flush()
    return refundable


async def create_invoice_payment(
    session: AsyncSession,
    arrangement: FeeArrangement,
    invoice_id: int,
    *,
    now: datetime | None = None,
) -> FeePayment:
    """Seller records an offline payment for a specific invoice → a Pending
    OrderValueInvoice FeePayment, linked to the invoice. Admin confirms it via
    confirm_invoice_payment. Caller commits."""
    now = now or datetime.now(timezone.utc)
    invoice = await session.get(FeeInvoice, invoice_id)
    if invoice is None or invoice.arrangement_id != arrangement.id:
        raise FeeError("invoice_not_found")
    if invoice.status not in (InvoiceStatus.Pending, InvoiceStatus.Overdue):
        raise FeeError("invoice_not_payable")
    if invoice.payment_id is not None:
        existing = await session.get(FeePayment, invoice.payment_id)
        if existing is not None and existing.status == FeePaymentStatus.Pending:
            raise FeeError("payment_already_pending")

    payment = FeePayment(
        arrangement_id=arrangement.id,
        kind=FeePaymentKind.OrderValueInvoice,
        amount=invoice.amount_due,
        status=FeePaymentStatus.Pending,
    )
    session.add(payment)
    await session.flush()
    invoice.payment_id = payment.id
    session.add(invoice)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.PaymentRecorded,
            amount_delta=invoice.amount_due,
            actor="seller",
            note=f"order-value invoice #{invoice_id} payment",
        )
    )
    await session.flush()
    return payment


async def confirm_invoice_payment(
    session: AsyncSession,
    payment: FeePayment,
    admin_user_id: int,
    *,
    today: date | None = None,
) -> tuple[FeeArrangement, NotificationType | None]:
    """Admin confirms an offline OrderValueInvoice payment. Marks the linked
    invoice Paid, subtracts it from the arrangement balance, and — if the
    arrangement was suspended FOR NON-PAYMENT and no unpaid invoices remain —
    reactivates it (records the single FeeReactivated in-app notification). An
    admin-terminated arrangement is NOT resurrected. Returns (arrangement,
    notification_type). Caller commits."""
    now = datetime.now(timezone.utc)
    payment.status = FeePaymentStatus.Confirmed
    payment.confirmed_by_admin_id = admin_user_id
    payment.confirmed_at = now
    session.add(payment)

    invoice = (
        await session.exec(
            select(FeeInvoice).where(FeeInvoice.payment_id == payment.id)
        )
    ).first()
    # Row-lock the arrangement to serialize concurrent confirm/forfeit/refund.
    arrangement = (
        await session.exec(
            select(FeeArrangement)
            .where(FeeArrangement.id == payment.arrangement_id)
            .with_for_update()
        )
    ).one()

    if invoice is not None and invoice.status != InvoiceStatus.Paid:
        invoice.status = InvoiceStatus.Paid
        invoice.paid_at = now
        session.add(invoice)
        arrangement.balance = round(arrangement.balance - invoice.amount_due, 2)

    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.InvoicePaid,
            amount_delta=payment.amount,
            actor=f"admin:{admin_user_id}",
            note="order-value invoice paid",
        )
    )
    session.add(arrangement)
    notif = await _reactivate_if_cleared(session, arrangement, f"admin:{admin_user_id}")
    await session.flush()
    return arrangement, notif
