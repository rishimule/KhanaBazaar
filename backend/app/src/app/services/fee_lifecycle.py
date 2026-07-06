# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Freebie-phase fee lifecycle: idempotent auto-enrollment of (store, service)
pairs into a Freebie Trial arrangement, and the daily sweep that expires trials
(Trial→Grace→Suspended), holding when no paid model is offerable.

Pure/service-layer logic; callers own the commit. Seller notifications +
expiry reminders are added in Plan 3."""
from datetime import date, datetime, timedelta, timezone

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
)
from app.models.profile import SellerProfileService
from app.models.store import Store
from app.services.fee_notifications import notify_seller_fee_event

DEFAULT_FREEBIE_DAYS = 30
DEFAULT_GRACE_DAYS = 2
_MONTH_DAYS = 30  # dependency-free month arithmetic for validity windows


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
    today = today or date.today()
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
    await session.flush()
    return counts
