# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Freebie-phase fee lifecycle: idempotent auto-enrollment of (store, service)
pairs into a Freebie Trial arrangement, and the daily sweep that expires trials
(Trial→Grace→Suspended), holding when no paid model is offerable.

Pure/service-layer logic; callers own the commit. Seller notifications +
expiry reminders are added in Plan 3."""
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import NotificationType
from app.models.platform_fee import (
    ArrangementStatus,
    FeeArrangement,
    FeeEvent,
    FeeEventType,
    FeeModel,
    FeePayment,
    FeePaymentKind,
    FeePaymentStatus,
    PlatformFeeSettings,
    ServiceFeeConfig,
    ServiceSubscriptionPlan,
    StoreCreditReason,
)
from app.models.profile import SellerProfileService
from app.models.store import Store
from app.services import store_credit
from app.services.fee_notifications import notify_seller_fee_event

DEFAULT_FREEBIE_DAYS = 30
DEFAULT_GRACE_DAYS = 2
_MONTH_DAYS = 30  # dependency-free month arithmetic for validity windows
# All fee dates are reckoned in IST (India-only marketplace) so billing-day and
# expiry comparisons don't drift with the worker's UTC clock.
IST = ZoneInfo("Asia/Kolkata")


async def _freebie_days_by_service(
    session: AsyncSession, service_ids: list[int]
) -> dict[int, int]:
    if not service_ids:
        return {}
    rows = (
        await session.exec(
            select(
                ServiceFeeConfig.service_id, ServiceFeeConfig.freebie_default_days
            ).where(ServiceFeeConfig.service_id.in_(service_ids))  # type: ignore[attr-defined]
        )
    ).all()
    return dict(rows)


async def sync_store_arrangements(
    session: AsyncSession, seller_profile_id: int, *, today: date | None = None
) -> None:
    """Ensure every service the seller currently offers has a Freebie Trial
    arrangement for their store; delete arrangements (and their events) for
    services no longer offered. No-op if the seller has no store yet. Idempotent
    — an existing arrangement is left untouched (its valid_until is preserved).
    Caller commits."""
    today = today or date.today()
    store = (
        await session.exec(
            select(Store).where(Store.seller_profile_id == seller_profile_id)
        )
    ).first()
    if store is None or store.id is None:
        return
    offered = set(
        (
            await session.exec(
                select(SellerProfileService.service_id).where(
                    SellerProfileService.seller_profile_id == seller_profile_id
                )
            )
        ).all()
    )
    existing_rows = (
        await session.exec(
            select(FeeArrangement).where(FeeArrangement.store_id == store.id)
        )
    ).all()
    existing = {r.service_id: r for r in existing_rows}

    to_create = [sid for sid in offered if sid not in existing]
    days_by_service = await _freebie_days_by_service(session, to_create)
    for sid in to_create:
        days = days_by_service.get(sid, DEFAULT_FREEBIE_DAYS)
        arr = FeeArrangement(
            store_id=store.id,
            service_id=sid,
            model=FeeModel.Freebie,
            status=ArrangementStatus.Trial,
            valid_until=today + timedelta(days=days),
        )
        session.add(arr)
        await session.flush()
        session.add(
            FeeEvent(
                arrangement_id=arr.id,
                event_type=FeeEventType.ArrangementCreated,
                actor="system",
                note=f"freebie trial {days}d",
            )
        )

    for sid, row in existing.items():
        if sid not in offered:
            # Freebie arrangement for a dropped service: remove it + its events
            # (no financial history to preserve). A re-add creates a fresh trial.
            events = (
                await session.exec(
                    select(FeeEvent).where(FeeEvent.arrangement_id == row.id)
                )
            ).all()
            for ev in events:
                await session.delete(ev)
            await session.delete(row)
    await session.flush()


class FeeError(Exception):
    """Invalid fee operation (bad opt-in, missing plan, etc.)."""


async def opt_into_subscription(
    session: AsyncSession,
    arrangement: FeeArrangement,
    duration_months: int,
    *,
    now: datetime | None = None,
) -> FeePayment:
    """Record a seller's intent to subscribe: create a Pending SubscriptionFee
    payment and mark the arrangement pending. Does NOT change the arrangement's
    commercial status/model/validity — that happens on admin confirmation.
    Caller commits. Raises FeeError if subscription isn't offerable, the plan is
    missing/inactive, or a pending payment already exists."""
    now = now or datetime.now(timezone.utc)
    cfg = (
        await session.exec(
            select(ServiceFeeConfig).where(
                ServiceFeeConfig.service_id == arrangement.service_id
            )
        )
    ).first()
    if cfg is None or not cfg.subscription_enabled:
        raise FeeError("subscription_not_offerable")
    plan = (
        await session.exec(
            select(ServiceSubscriptionPlan).where(
                ServiceSubscriptionPlan.service_id == arrangement.service_id,
                ServiceSubscriptionPlan.duration_months == duration_months,
                ServiceSubscriptionPlan.is_active == True,  # noqa: E712
            )
        )
    ).first()
    if plan is None:
        raise FeeError("plan_not_available")

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

    arrangement.pending_since = now
    arrangement.queued_model = FeeModel.Subscription
    arrangement.queued_duration_months = duration_months
    session.add(arrangement)
    payment = FeePayment(
        arrangement_id=arrangement.id,
        kind=FeePaymentKind.SubscriptionFee,
        amount=plan.price,
        status=FeePaymentStatus.Pending,
    )
    session.add(payment)
    await session.flush()
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.PaymentRecorded,
            amount_delta=plan.price,
            actor="seller",
            note=f"opt-in subscription {duration_months}m",
        )
    )
    return payment


async def confirm_subscription_payment(
    session: AsyncSession,
    payment: FeePayment,
    admin_user_id: int,
    *,
    today: date | None = None,
) -> FeeArrangement:
    """Admin confirms an offline SubscriptionFee payment → activate the
    arrangement. Stacks onto the current expiry when renewing early, else starts
    from today. Caller commits."""
    today = today or date.today()
    arrangement = (
        await session.exec(
            select(FeeArrangement).where(FeeArrangement.id == payment.arrangement_id)
        )
    ).one()
    duration = arrangement.queued_duration_months or 0
    if duration <= 0:
        raise FeeError("no_queued_duration")

    span = timedelta(days=duration * _MONTH_DAYS)
    if (
        arrangement.status == ArrangementStatus.Active
        and arrangement.valid_until is not None
        and today <= arrangement.valid_until
    ):
        new_valid_until = arrangement.valid_until + span  # renew early → stack
        event_type = FeeEventType.Renewed
    else:
        new_valid_until = today + span  # fresh / lapsed / reactivate
        event_type = FeeEventType.Activated

    arrangement.model = FeeModel.Subscription
    arrangement.status = ArrangementStatus.Active
    arrangement.subscription_duration_months = duration
    arrangement.price_snapshot = payment.amount
    arrangement.valid_until = new_valid_until
    arrangement.pending_since = None
    arrangement.queued_model = None
    arrangement.queued_duration_months = None
    arrangement.suspended_at = None
    arrangement.suspended_reason = None
    session.add(arrangement)

    payment.status = FeePaymentStatus.Confirmed
    payment.confirmed_by_admin_id = admin_user_id
    payment.confirmed_at = datetime.now(timezone.utc)
    session.add(payment)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=event_type,
            amount_delta=payment.amount,
            actor=f"admin:{admin_user_id}",
            note=f"subscription {duration}m → {new_valid_until.isoformat()}",
        )
    )
    await session.flush()
    return arrangement


async def reject_payment(
    session: AsyncSession, payment: FeePayment, admin_user_id: int, reason: str
) -> None:
    """Admin rejects a pending payment: mark it rejected, clear the arrangement's
    pending markers, leave its commercial state untouched. Caller commits."""
    payment.status = FeePaymentStatus.Rejected
    payment.reject_reason = reason
    payment.confirmed_by_admin_id = admin_user_id
    payment.confirmed_at = datetime.now(timezone.utc)
    session.add(payment)
    arrangement = (
        await session.exec(
            select(FeeArrangement).where(FeeArrangement.id == payment.arrangement_id)
        )
    ).one()
    arrangement.pending_since = None
    arrangement.queued_model = None
    arrangement.queued_duration_months = None
    session.add(arrangement)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.PaymentRejected,
            actor=f"admin:{admin_user_id}",
            note=reason,
        )
    )
    await session.flush()


def request_cancellation(session: AsyncSession, arrangement: FeeArrangement) -> None:
    """Seller cancels auto-renewal; the arrangement runs to its paid expiry then
    the sweep suspends it. Non-refundable. Caller commits."""
    arrangement.cancel_requested = True
    arrangement.auto_renew = False
    session.add(arrangement)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.ModelChanged,
            actor="seller",
            note="cancellation requested",
        )
    )


def admin_extend(
    session: AsyncSession, arrangement: FeeArrangement, days: int, admin_user_id: int
) -> None:
    """Push the arrangement's validity out by `days` (from its current expiry,
    or today if none). Caller commits + audits."""
    base = arrangement.valid_until or date.today()
    arrangement.valid_until = base + timedelta(days=days)
    session.add(arrangement)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.Extended,
            actor=f"admin:{admin_user_id}",
            note=f"+{days}d → {arrangement.valid_until.isoformat()}",
        )
    )


def admin_terminate(
    session: AsyncSession, arrangement: FeeArrangement, reason: str, admin_user_id: int
) -> None:
    """Force-suspend immediately + stop auto-renew. Caller commits + audits."""
    arrangement.status = ArrangementStatus.Suspended
    arrangement.suspended_at = datetime.now(timezone.utc)
    arrangement.suspended_reason = reason
    arrangement.auto_renew = False
    session.add(arrangement)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.Terminated,
            actor=f"admin:{admin_user_id}",
            note=reason,
        )
    )


def admin_comp_subscription(
    session: AsyncSession,
    arrangement: FeeArrangement,
    duration_months: int,
    admin_user_id: int,
    *,
    today: date | None = None,
) -> None:
    """Comp: activate as Subscription for `duration_months` with no payment
    (price_snapshot=0). Bypasses opt-in gating (admin authority). Caller commits
    + audits."""
    today = today or date.today()
    arrangement.model = FeeModel.Subscription
    arrangement.status = ArrangementStatus.Active
    arrangement.subscription_duration_months = duration_months
    arrangement.price_snapshot = 0.0
    arrangement.valid_until = today + timedelta(days=duration_months * _MONTH_DAYS)
    arrangement.pending_since = None
    arrangement.queued_model = None
    arrangement.queued_duration_months = None
    arrangement.suspended_at = None
    arrangement.suspended_reason = None
    arrangement.cancel_requested = False
    arrangement.auto_renew = True
    session.add(arrangement)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=FeeEventType.Activated,
            amount_delta=0.0,
            actor=f"admin:{admin_user_id}",
            note=f"comp subscription {duration_months}m",
        )
    )


async def _paid_model_offerable(
    session: AsyncSession, service_ids: set[int]
) -> dict[int, bool]:
    """True for a service if the admin has enabled ANY paid model for it."""
    if not service_ids:
        return {}
    rows = (
        await session.exec(
            select(
                ServiceFeeConfig.service_id,
                ServiceFeeConfig.subscription_enabled,
                ServiceFeeConfig.order_value_enabled,
                ServiceFeeConfig.pay_per_txn_enabled,
            ).where(ServiceFeeConfig.service_id.in_(service_ids))  # type: ignore[attr-defined]
        )
    ).all()
    return {sid: bool(sub or ov or ppt) for sid, sub, ov, ppt in rows}


def _suspend(session: AsyncSession, arr: FeeArrangement, reason: str) -> None:
    arr.status = ArrangementStatus.Suspended
    arr.suspended_at = datetime.now(timezone.utc)
    arr.suspended_reason = reason
    session.add(arr)
    session.add(
        FeeEvent(
            arrangement_id=arr.id,
            event_type=FeeEventType.Suspended,
            actor="system",
            note=reason,
        )
    )


async def run_fee_sweep(
    session: AsyncSession,
    today: date | None = None,
    *,
    notices: list[tuple[int, str, str | None]] | None = None,
) -> dict[str, int]:
    """Advance dated arrangements: expired Trial/Active → Grace (or Suspended if
    grace=0), Grace past its window → Suspended. A Freebie whose service has no
    offerable paid model is HELD (never stranded). Caller commits.

    When `notices` is provided, appends `(seller_profile_id, type_value,
    until_iso)` for each fee notification recorded during the sweep, so the
    caller can fan out to other channels (SMS/WhatsApp/email) post-commit."""
    today = today or datetime.now(IST).date()
    settings_row = (
        await session.exec(
            select(PlatformFeeSettings).order_by(PlatformFeeSettings.id).limit(1)  # type: ignore[arg-type]
        )
    ).first()
    grace_days = settings_row.grace_period_days if settings_row else DEFAULT_GRACE_DAYS
    protect_days = (
        settings_row.pending_payment_protect_days if settings_row else 7
    )
    reminder_days = (
        settings_row.expiry_reminder_start_days if settings_row else 7
    )

    rows = (
        await session.exec(
            select(FeeArrangement).where(
                FeeArrangement.model != FeeModel.PayPerTransaction,  # PPT: dedicated pass below
                FeeArrangement.status.in_(  # type: ignore[attr-defined]
                    [
                        ArrangementStatus.Trial,
                        ArrangementStatus.Active,
                        ArrangementStatus.Grace,
                    ]
                ),
                FeeArrangement.valid_until.is_not(None),  # type: ignore[union-attr]
            )
        )
    ).all()
    paid_offerable = await _paid_model_offerable(session, {r.service_id for r in rows})
    already_held = set(
        (
            await session.exec(
                select(FeeEvent.arrangement_id).where(
                    FeeEvent.event_type == FeeEventType.TrialHeld,
                    FeeEvent.arrangement_id.in_([r.id for r in rows]),  # type: ignore[union-attr]
                )
            )
        ).all()
    ) if rows else set()
    counts = {"to_grace": 0, "to_suspended": 0, "held": 0, "protected": 0, "reminded": 0}

    for arr in rows:
        assert arr.valid_until is not None
        if (
            arr.pending_since is not None
            and (today - arr.pending_since.date()) <= timedelta(days=protect_days)
        ):
            counts["protected"] += 1
            continue
        is_held_exempt = arr.model == FeeModel.Freebie and not paid_offerable.get(
            arr.service_id, False
        )
        if arr.status in (ArrangementStatus.Trial, ArrangementStatus.Active):
            if today <= arr.valid_until:
                # Approaching expiry (and will actually expire) → daily reminder.
                if (
                    not is_held_exempt
                    and (arr.valid_until - today) <= timedelta(days=reminder_days)
                    and arr.last_reminder_sent_on != today
                ):
                    arr.last_reminder_sent_on = today
                    session.add(arr)
                    spid = await notify_seller_fee_event(
                        session, store_id=arr.store_id,
                        type=NotificationType.FeeExpiring, valid_until=arr.valid_until,
                    )
                    if notices is not None and spid is not None:
                        notices.append(
                            (spid, NotificationType.FeeExpiring.value, arr.valid_until.isoformat())
                        )
                    counts["reminded"] += 1
                continue
            if is_held_exempt:
                if arr.id not in already_held:
                    already_held.add(arr.id)
                    session.add(
                        FeeEvent(
                            arrangement_id=arr.id,
                            event_type=FeeEventType.TrialHeld,
                            actor="system",
                            note="held: no paid model offerable",
                        )
                    )
                counts["held"] += 1
                continue
            if grace_days > 0:
                arr.status = ArrangementStatus.Grace
                session.add(arr)
                session.add(
                    FeeEvent(
                        arrangement_id=arr.id,
                        event_type=FeeEventType.GraceStarted,
                        actor="system",
                    )
                )
                counts["to_grace"] += 1
            else:
                _suspend(session, arr, "expired")
                spid = await notify_seller_fee_event(
                    session, store_id=arr.store_id, type=NotificationType.FeeSuspended,
                )
                if notices is not None and spid is not None:
                    notices.append((spid, NotificationType.FeeSuspended.value, None))
                counts["to_suspended"] += 1
        elif arr.status == ArrangementStatus.Grace:
            if today > arr.valid_until + timedelta(days=grace_days):
                _suspend(session, arr, "grace_elapsed")
                spid = await notify_seller_fee_event(
                    session, store_id=arr.store_id, type=NotificationType.FeeSuspended,
                )
                if notices is not None and spid is not None:
                    notices.append((spid, NotificationType.FeeSuspended.value, None))
                counts["to_suspended"] += 1

    # ── Pay-Per-Transaction pass (balance-driven, no time expiry) ──
    ppt_rows = (
        await session.exec(
            select(FeeArrangement).where(
                FeeArrangement.model == FeeModel.PayPerTransaction,
                FeeArrangement.status.in_(  # type: ignore[attr-defined]
                    [ArrangementStatus.Active, ArrangementStatus.Grace]
                ),
            )
        )
    ).all()
    for arr in ppt_rows:
        try:
            fee, _min_dep, low_thr = await _ppt_config(session, arr.service_id)
        except FeeError:
            continue  # config removed/disabled → leave the arrangement alone
        if arr.status == ArrangementStatus.Active:
            if arr.balance < fee:
                arr.status = ArrangementStatus.Grace
                arr.valid_until = today
                session.add(arr)
                session.add(
                    FeeEvent(
                        arrangement_id=arr.id, event_type=FeeEventType.GraceStarted,
                        actor="system", note="sweep: balance below fee",
                    )
                )
                # Grace-start: store still live → "top up" nudge, not "suspended".
                spid = await notify_seller_fee_event(
                    session, store_id=arr.store_id, type=NotificationType.FeeLowBalance,
                )
                if notices is not None and spid is not None:
                    notices.append((spid, NotificationType.FeeLowBalance.value, None))
                counts["to_grace"] += 1
            elif arr.balance < low_thr and arr.last_reminder_sent_on != today:
                arr.last_reminder_sent_on = today
                session.add(arr)
                spid = await notify_seller_fee_event(
                    session, store_id=arr.store_id, type=NotificationType.FeeLowBalance,
                )
                if notices is not None and spid is not None:
                    notices.append((spid, NotificationType.FeeLowBalance.value, None))
                counts["reminded"] += 1
        elif arr.status == ArrangementStatus.Grace:
            if arr.balance >= fee:
                arr.status = ArrangementStatus.Active
                arr.valid_until = None
                session.add(arr)
                session.add(
                    FeeEvent(
                        arrangement_id=arr.id, event_type=FeeEventType.Reactivated,
                        actor="system", note="sweep: balance restored",
                    )
                )
            elif (
                arr.valid_until is not None
                and today > arr.valid_until + timedelta(days=grace_days)
            ):
                _suspend(session, arr, "pay_per_txn_exhausted")
                spid = await notify_seller_fee_event(
                    session, store_id=arr.store_id, type=NotificationType.FeeSuspended,
                )
                if notices is not None and spid is not None:
                    notices.append((spid, NotificationType.FeeSuspended.value, None))
                counts["to_suspended"] += 1

    # ── Order Value % pass (postpaid monthly invoicing + overdue suspension) ──
    # Lazy import: fee_order_value imports from this module, so importing it at
    # module load would create a cycle.
    from app.services.fee_order_value import (
        generate_order_value_invoices,
        sweep_order_value_overdue,
    )

    counts["invoices_raised"] = await generate_order_value_invoices(
        session, today, notices=notices
    )
    ov = await sweep_order_value_overdue(session, today, notices=notices)
    counts["ov_overdue"] = ov["overdue"]
    counts["to_suspended"] += ov["suspended"]

    await session.flush()
    return counts


# ─── Pay-Per-Transaction (prepaid) ──────────────────────────────────────────


async def _ppt_config(
    session: AsyncSession, service_id: int
) -> tuple[float, float, float]:
    """Return (fee, min_deposit, low_balance_threshold) for a service that has
    PPT enabled. Raises FeeError if PPT is not offerable."""
    cfg = (
        await session.exec(
            select(
                ServiceFeeConfig.pay_per_txn_enabled,
                ServiceFeeConfig.pay_per_txn_fee,
                ServiceFeeConfig.pay_per_txn_min_deposit,
                ServiceFeeConfig.pay_per_txn_low_balance_threshold,
            ).where(ServiceFeeConfig.service_id == service_id)
        )
    ).first()
    if cfg is None or not cfg[0]:
        raise FeeError("pay_per_txn_not_offerable")
    return float(cfg[1]), float(cfg[2]), float(cfg[3])


async def _evaluate_ppt_status(
    session: AsyncSession, arr: FeeArrangement, *, today: date | None = None,
    notify: bool = True, allow_unsuspend: bool = True,
) -> None:
    """Drive PPT balance→status transitions after any balance change. Reads the
    LIVE fee. Records events + (when `notify`) an in-app seller notification.
    Sets/clears the grace deadline in `valid_until`. Caller commits.

    - Active, balance < fee   → Grace (valid_until = today).
    - Active, balance < thr   → throttled low-balance reminder.
    - Grace, balance ≥ fee    → Active (reactivate).
    - Suspended, balance ≥ fee → Active ONLY when `allow_unsuspend` (deliberate
      top-up/credit-apply). A passive cancel-refund passes allow_unsuspend=False
      so it never un-suspends a store (spec §8 / edge-case 6).

    The Grace→Suspend transition is time-driven and fires only from the sweep."""
    today = today or date.today()
    fee, _min_dep, low_thr = await _ppt_config(session, arr.service_id)

    if arr.status in (ArrangementStatus.Grace, ArrangementStatus.Suspended):
        can_reactivate = arr.status == ArrangementStatus.Grace or allow_unsuspend
        if arr.balance >= fee and can_reactivate:
            arr.status = ArrangementStatus.Active
            arr.valid_until = None
            arr.suspended_at = None
            arr.suspended_reason = None
            session.add(arr)
            session.add(
                FeeEvent(
                    arrangement_id=arr.id, event_type=FeeEventType.Reactivated,
                    actor="system", note="balance restored",
                )
            )
            if notify:
                await notify_seller_fee_event(
                    session, store_id=arr.store_id,
                    type=NotificationType.FeeReactivated,
                )
        await session.flush()
        return

    if arr.status == ArrangementStatus.Active:
        if arr.balance < fee:
            arr.status = ArrangementStatus.Grace
            arr.valid_until = today
            session.add(arr)
            session.add(
                FeeEvent(
                    arrangement_id=arr.id, event_type=FeeEventType.GraceStarted,
                    actor="system", note="balance below fee",
                )
            )
            # Grace-start: the store is still LIVE (in grace) — a "top up" nudge,
            # not a "suspended" message. Actual suspension notifies from the sweep.
            if notify:
                await notify_seller_fee_event(
                    session, store_id=arr.store_id,
                    type=NotificationType.FeeLowBalance,
                )
        elif arr.balance < low_thr and arr.last_reminder_sent_on != today:
            arr.last_reminder_sent_on = today
            session.add(arr)
            if notify:
                await notify_seller_fee_event(
                    session, store_id=arr.store_id,
                    type=NotificationType.FeeLowBalance,
                )
    await session.flush()


async def opt_into_pay_per_transaction(
    session: AsyncSession, arrangement: FeeArrangement, deposit_amount: float,
    *, use_credit: bool = False, now: datetime | None = None,
) -> FeePayment | None:
    """Seller opts into PPT with an initial prepaid deposit. When `use_credit`
    and the store's wallet credit fully covers `deposit_amount`, apply credit +
    activate immediately (returns None). Otherwise create a pending cash
    FeePayment for the full deposit (partial credit is NOT blended here — sellers
    mix credit post-activation via apply-credit). Caller commits."""
    now = now or datetime.now(timezone.utc)
    _fee, min_deposit, _low = await _ppt_config(session, arrangement.service_id)
    if deposit_amount < min_deposit:
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

    if use_credit:
        store = await store_credit.load_store(session, arrangement.store_id)
        if store.fee_credit_balance >= deposit_amount:
            applied = await store_credit.apply(
                session, store, deposit_amount, actor="seller",
                note="ppt opt-in (credit)", related_arrangement_id=arrangement.id,
            )
            arrangement.model = FeeModel.PayPerTransaction
            arrangement.status = ArrangementStatus.Active
            arrangement.balance = applied
            arrangement.valid_until = None
            arrangement.pending_since = None
            session.add(arrangement)
            session.add(
                FeeEvent(
                    arrangement_id=arrangement.id, event_type=FeeEventType.Activated,
                    amount_delta=applied, actor="seller",
                    note="ppt activated via credit",
                )
            )
            await session.flush()
            return None

    arrangement.model = FeeModel.PayPerTransaction
    arrangement.status = ArrangementStatus.PendingActivation
    arrangement.pending_since = now
    session.add(arrangement)
    payment = FeePayment(
        arrangement_id=arrangement.id, kind=FeePaymentKind.PayPerTxnTopUp,
        amount=deposit_amount, status=FeePaymentStatus.Pending,
    )
    session.add(payment)
    await session.flush()
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id, event_type=FeeEventType.PaymentRecorded,
            amount_delta=deposit_amount, actor="seller", note="ppt opt-in deposit",
        )
    )
    return payment


async def confirm_pay_per_txn_topup(
    session: AsyncSession, payment: FeePayment, admin_user_id: int,
    *, today: date | None = None,
) -> tuple[FeeArrangement, NotificationType | None]:
    """Admin confirms an offline PPT deposit/top-up. Credits balance, activates
    a pending arrangement, and auto-reactivates a Grace/Suspended one. Returns
    (arrangement, notification_type) — the single in-app notification is recorded
    here (FeeActivated for a first activation, FeeReactivated for a reactivating
    top-up, else None); the caller does channel fan-out only. Caller commits."""
    arrangement = (
        await session.exec(
            select(FeeArrangement).where(FeeArrangement.id == payment.arrangement_id)
        )
    ).one()
    was_activation = arrangement.status == ArrangementStatus.PendingActivation
    prev_status = arrangement.status

    arrangement.balance = round(arrangement.balance + payment.amount, 2)
    arrangement.model = FeeModel.PayPerTransaction
    arrangement.pending_since = None

    payment.status = FeePaymentStatus.Confirmed
    payment.confirmed_by_admin_id = admin_user_id
    payment.confirmed_at = datetime.now(timezone.utc)
    session.add(payment)

    session.add(
        FeeEvent(
            arrangement_id=arrangement.id,
            event_type=(
                FeeEventType.Activated if was_activation else FeeEventType.BalanceTopup
            ),
            amount_delta=payment.amount, actor=f"admin:{admin_user_id}",
            note="ppt deposit" if was_activation else "ppt top-up",
        )
    )

    if was_activation:
        arrangement.status = ArrangementStatus.Active
        arrangement.valid_until = None
    session.add(arrangement)
    await session.flush()
    # Correct an underfunded activation (deposit < fee) → Grace, and reactivate a
    # Grace/Suspended top-up. notify=False: this function owns the single in-app
    # notification below.
    await _evaluate_ppt_status(session, arrangement, today=today, notify=False)

    notif: NotificationType | None = None
    if was_activation:
        notif = NotificationType.FeeActivated
    elif (
        prev_status in (ArrangementStatus.Grace, ArrangementStatus.Suspended)
        and arrangement.status == ArrangementStatus.Active
    ):
        notif = NotificationType.FeeReactivated
    if notif is not None:
        await notify_seller_fee_event(
            session, store_id=arrangement.store_id, type=notif
        )
    await session.flush()
    return arrangement, notif


async def create_top_up(
    session: AsyncSession, arrangement: FeeArrangement, amount: float,
    *, now: datetime | None = None,
) -> FeePayment:
    """Seller records an offline cash top-up → a Pending PayPerTxnTopUp payment
    (admin confirms via confirm_pay_per_txn_topup). Caller commits."""
    if arrangement.model != FeeModel.PayPerTransaction:
        raise FeeError("not_pay_per_transaction")
    if amount <= 0:
        raise FeeError("bad_amount")
    existing = (
        await session.exec(
            select(FeePayment).where(
                FeePayment.arrangement_id == arrangement.id,
                FeePayment.status == FeePaymentStatus.Pending,
            )
        )
    ).first()
    if existing is not None:
        raise FeeError("payment_already_pending")
    payment = FeePayment(
        arrangement_id=arrangement.id, kind=FeePaymentKind.PayPerTxnTopUp,
        amount=amount, status=FeePaymentStatus.Pending,
    )
    session.add(payment)
    await session.flush()
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id, event_type=FeeEventType.PaymentRecorded,
            amount_delta=amount, actor="seller", note="ppt top-up",
        )
    )
    return payment


async def apply_credit_to_arrangement(
    session: AsyncSession, arrangement: FeeArrangement, amount: float,
    *, today: date | None = None,
) -> float:
    """Instantly move store wallet credit into a PPT arrangement's balance (no
    admin step — platform-held money). Reactivates Grace/Suspended if it clears
    the fee threshold. Returns applied amount. Caller commits."""
    if arrangement.model != FeeModel.PayPerTransaction:
        raise FeeError("not_pay_per_transaction")
    if amount <= 0:
        raise FeeError("bad_amount")
    store = await store_credit.load_store(session, arrangement.store_id)
    if amount > store.fee_credit_balance:
        # Reject over-requests rather than silently clamping (spec §16.10).
        raise FeeError("amount_exceeds_credit")
    applied = await store_credit.apply(
        session, store, amount, actor="seller", note="ppt balance top-up",
        related_arrangement_id=arrangement.id,
    )
    if applied <= 0:
        raise FeeError("no_credit_available")
    arrangement.balance = round(arrangement.balance + applied, 2)
    session.add(arrangement)
    session.add(
        FeeEvent(
            arrangement_id=arrangement.id, event_type=FeeEventType.BalanceTopup,
            amount_delta=applied, actor="seller", note="credit applied",
        )
    )
    await session.flush()
    await _evaluate_ppt_status(session, arrangement, today=today)
    return applied


async def _dispose_ppt_balance(
    session: AsyncSession, arr: FeeArrangement, *,
    disposition: Literal["credit", "cash_out", "waive"], actor: str, note: str,
) -> None:
    """Dispose of a PPT arrangement's leftover balance on exit. Positive →
    wallet credit (or cash-out); negative → recorded owed (waive zeroes it).
    Zeroes arr.balance. Caller commits."""
    store = await store_credit.load_store(session, arr.store_id)
    bal = arr.balance
    if bal > 0:
        session.add(
            FeeEvent(
                arrangement_id=arr.id, event_type=FeeEventType.BalanceRefunded,
                amount_delta=-bal, actor=actor, note=note,
            )
        )
        await store_credit.grant(
            session, store, bal, actor=actor, note=f"ppt exit: {note}",
            reason=StoreCreditReason.GrantedOnExit, related_arrangement_id=arr.id,
        )
        if disposition == "cash_out":
            await store_credit.cash_out(
                session, store, bal, actor=actor, note=f"ppt exit refund: {note}"
            )
    elif bal < 0:
        # Debt lives on arr.balance (negative). Disposing zeroes it and records
        # the event — money-neutral to the store wallet (waiving must NOT mint
        # spendable credit). `waive` forgives; `credit`/`cash_out` record the
        # amount as best-effort owed (no automated collection).
        owed = -bal
        note_txt = (
            f"debt {owed} waived: {note}"
            if disposition == "waive"
            else f"debt {owed} owed (best-effort): {note}"
        )
        session.add(
            FeeEvent(
                arrangement_id=arr.id, event_type=FeeEventType.BalanceRefunded,
                amount_delta=owed, actor=actor, note=note_txt,
            )
        )
    arr.balance = 0.0
    session.add(arr)
    await session.flush()


async def seller_switch_from_ppt(
    session: AsyncSession, arr: FeeArrangement
) -> None:
    """Seller leaves PPT voluntarily. Blocked on a negative balance (must settle
    first). Positive balance → wallet credit; arrangement terminated. Caller
    commits."""
    if arr.model != FeeModel.PayPerTransaction:
        raise FeeError("not_pay_per_transaction")
    if arr.balance < 0:
        raise FeeError("balance_negative")
    await _dispose_ppt_balance(
        session, arr, disposition="credit", actor="seller", note="seller switch"
    )
    arr.status = ArrangementStatus.Suspended
    arr.suspended_at = datetime.now(timezone.utc)
    arr.suspended_reason = "switched_from_ppt"
    session.add(arr)
    session.add(
        FeeEvent(
            arrangement_id=arr.id, event_type=FeeEventType.Terminated,
            actor="seller", note="switched from ppt",
        )
    )
    await session.flush()


async def admin_switch_model(
    session: AsyncSession, arr: FeeArrangement, *,
    target_model: FeeModel, target_duration_months: Optional[int] = None,
    disposition: Literal["credit", "cash_out", "waive"] = "credit",
    admin_user_id: int, today: date | None = None,
) -> None:
    """Admin force-switches an arrangement to `target_model` at ANY balance
    (disposes leftover PPT balance per `disposition`). Bypasses seller guards +
    gating. Caller commits + audits."""
    today = today or datetime.now(IST).date()
    if arr.model == FeeModel.PayPerTransaction:
        await _dispose_ppt_balance(
            session, arr, disposition=disposition, actor=f"admin:{admin_user_id}",
            note="admin switch",
        )
    elif arr.model == FeeModel.OrderValuePercent:
        # Bill trailing sales + settle the deposit before switching, so the
        # balance/deposit are never silently discarded. Lazy import: avoids the
        # fee_lifecycle <-> fee_order_value cycle.
        from app.services.fee_order_value import settle_order_value_exit

        await settle_order_value_exit(
            session, arr, today, disposition=disposition, admin_user_id=admin_user_id
        )
    if target_model == FeeModel.Subscription:
        if not target_duration_months:
            raise FeeError("duration_required")
        admin_comp_subscription(
            session, arr, target_duration_months, admin_user_id, today=today
        )
    elif target_model == FeeModel.Freebie:
        days_row = (
            await session.exec(
                select(ServiceFeeConfig.freebie_default_days).where(
                    ServiceFeeConfig.service_id == arr.service_id
                )
            )
        ).first()
        days = int(days_row) if days_row is not None else DEFAULT_FREEBIE_DAYS
        arr.model = FeeModel.Freebie
        arr.status = ArrangementStatus.Trial
        arr.valid_until = today + timedelta(days=days)
        arr.balance = 0.0
        arr.pending_since = None
        arr.suspended_at = None
        arr.suspended_reason = None
        session.add(arr)
        session.add(
            FeeEvent(
                arrangement_id=arr.id, event_type=FeeEventType.ModelChanged,
                actor=f"admin:{admin_user_id}", note=f"switched to freebie {days}d",
            )
        )
    else:
        raise FeeError("unsupported_target_model")
    await session.flush()
