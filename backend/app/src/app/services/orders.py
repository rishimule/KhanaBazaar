# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import hmac
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.otp import generate_code
from app.models.address import Address
from app.models.admin_audit import AdminActionTargetType
from app.models.base import User, UserRole
from app.models.commerce import (
    Delivery,
    DeliveryMode,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.profile import CustomerProfile, SellerProfile, VerificationStatus
from app.models.store import Store
from app.schemas.address import AddressPayload, address_from_payload
from app.services.admin_audit import log as audit_log
from app.services.inventory import lock_inventory_rows, restock
from app.utils.address import format_address

LEGAL_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.Pending: {OrderStatus.Packed, OrderStatus.Cancelled},
    OrderStatus.Packed: {OrderStatus.Dispatched, OrderStatus.Cancelled},
    OrderStatus.Dispatched: {OrderStatus.Delivered, OrderStatus.Cancelled},
    OrderStatus.Delivered: set(),
    OrderStatus.Cancelled: set(),
}

TARGET_BY_STR: dict[str, OrderStatus] = {
    "packed": OrderStatus.Packed,
    "dispatched": OrderStatus.Dispatched,
    "delivered": OrderStatus.Delivered,
}


def _order_snapshot(order: Order, payment: Optional[Payment]) -> dict[str, Any]:
    return {
        "id": order.id,
        "status": order.status.value,
        "service_id": order.service_id,
        "payment_status": payment.status.value if payment else None,
    }


async def _resolve_seller_id_for_store(session: AsyncSession, store_id: int) -> int:
    result = await session.exec(
        select(Store.seller_profile_id).where(Store.id == store_id)
    )
    seller_id = result.first()
    if seller_id is None:
        raise RuntimeError(f"Store {store_id} has no seller_profile_id")
    return seller_id


async def _assert_seller_active_for_store(
    session: AsyncSession, store_id: int
) -> None:
    seller_id = await _resolve_seller_id_for_store(session, store_id)
    profile = await session.get(SellerProfile, seller_id)
    if profile is None or profile.verification_status != VerificationStatus.Approved:
        raise HTTPException(
            status_code=409, detail={"code": "seller_not_active"}
        )


async def _seller_owns_store(session: AsyncSession, user: User, store_id: int) -> bool:
    profile_result = await session.exec(
        select(SellerProfile.id).where(SellerProfile.user_id == user.id)
    )
    profile_id = profile_result.first()
    if profile_id is None:
        return False
    store_result = await session.exec(
        select(Store.id).where(Store.id == store_id, Store.seller_profile_id == profile_id)
    )
    return store_result.first() is not None


async def transition_order_status(
    session: AsyncSession,
    order: Order,
    target_str: Literal["packed", "dispatched", "delivered"],
    actor: User,
    *,
    otp: Optional[str] = None,
    reason: Optional[str] = None,
) -> Order:
    target = TARGET_BY_STR[target_str]
    if target not in LEGAL_TRANSITIONS.get(order.status, set()):
        raise HTTPException(status_code=409, detail={
            "detail": "illegal_transition", "from": order.status.value, "to": target.value,
        })

    # Authorization: seller owns store or admin.
    if actor.role == UserRole.Seller:
        if not await _seller_owns_store(session, actor, order.store_id):
            raise HTTPException(status_code=403, detail="forbidden")
    elif actor.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="forbidden")

    acting_admin_id = actor.id if actor.role == UserRole.Admin else None
    if acting_admin_id is not None:
        await _assert_seller_active_for_store(session, order.store_id)

    delivery_result = await session.exec(select(Delivery).where(Delivery.order_id == order.id))
    delivery = delivery_result.first()
    if delivery is None:
        raise HTTPException(status_code=500, detail="delivery_missing")
    payment_result = await session.exec(select(Payment).where(Payment.order_id == order.id))
    payment = payment_result.first()

    before = _order_snapshot(order, payment)

    now = datetime.now(timezone.utc)

    # Delivery-OTP gate — runs BEFORE order.status is mutated so a failed
    # verification never persists a delivered status.
    if target == OrderStatus.Delivered:
        if actor.role == UserRole.Admin:
            # Admin force-deliver escape hatch: reason required, audited below.
            if not reason or len(reason.strip()) < 10:
                raise HTTPException(
                    status_code=422, detail={"code": "reason_required"}
                )
        else:
            if delivery.delivery_otp is None:
                raise HTTPException(
                    status_code=409, detail={"code": "delivery_otp_not_issued"}
                )
            if delivery.delivery_otp_attempts >= settings.DELIVERY_OTP_MAX_ATTEMPTS:
                raise HTTPException(
                    status_code=409, detail={"code": "delivery_otp_locked"}
                )
            if not otp:
                raise HTTPException(
                    status_code=422, detail={"code": "delivery_otp_required"}
                )
            # `otp.isascii()` short-circuits before compare_digest, which raises
            # TypeError on non-ASCII str input — a non-ASCII code counts as a
            # wrong attempt (no 500, no counter bypass).
            if not (otp.isascii() and hmac.compare_digest(otp, delivery.delivery_otp)):
                delivery.delivery_otp_attempts += 1
                # Capture before commit() expires the instance (reading the
                # attribute afterwards would trigger a lazy load → MissingGreenlet).
                attempts_now = delivery.delivery_otp_attempts
                await session.commit()  # persist failed attempt; order.status untouched
                remaining = max(
                    0, settings.DELIVERY_OTP_MAX_ATTEMPTS - attempts_now
                )
                raise HTTPException(
                    status_code=422,
                    detail={"code": "delivery_otp_invalid", "remaining": remaining},
                )

    order.status = target
    if target == OrderStatus.Packed:
        delivery.status = DeliveryStatus.Packed
        delivery.packed_at = now
    elif target == OrderStatus.Dispatched:
        delivery.status = DeliveryStatus.Dispatched
        delivery.dispatched_at = now
        delivery.delivery_otp = generate_code()
        delivery.delivery_otp_attempts = 0
        delivery.delivery_otp_sent_at = now
        delivery.delivery_otp_verified_at = None
    elif target == OrderStatus.Delivered:
        delivery.status = DeliveryStatus.Delivered
        delivery.delivered_at = now
        if actor.role != UserRole.Admin:
            delivery.delivery_otp_verified_at = now
        delivery.delivery_otp = None  # consume the code (also clears it for admin force)
        # Credit orders are NOT paid on delivery — the customer still owes on
        # credit; the credit ledger, not Payment.status, tracks what's owed.
        if payment is not None and payment.method != PaymentMethod.Credit:
            payment.status = PaymentStatus.Paid
            payment.paid_at = now

    if acting_admin_id is not None:
        target_seller_id = await _resolve_seller_id_for_store(session, order.store_id)
        await audit_log(
            session=session,
            admin_user_id=acting_admin_id,
            target_seller_id=target_seller_id,
            target_type=AdminActionTargetType.Order,
            target_id=order.id,
            action=(
                "order.force_deliver"
                if target == OrderStatus.Delivered
                else "order.transition"
            ),
            before_json=before,
            after_json=_order_snapshot(order, payment),
            reason=reason.strip() if reason else None,
        )

    await session.commit()
    await session.refresh(order)
    return order


async def _authorize_cancel(session: AsyncSession, actor: User, order: Order) -> None:
    if actor.role == UserRole.Customer:
        if order.status != OrderStatus.Pending:
            raise HTTPException(status_code=403, detail="cancel_not_allowed")
        cust_result = await session.exec(
            select(CustomerProfile.id).where(CustomerProfile.user_id == actor.id)
        )
        if cust_result.first() != order.customer_profile_id:
            raise HTTPException(status_code=403, detail="forbidden")
    elif actor.role == UserRole.Seller:
        if not await _seller_owns_store(session, actor, order.store_id):
            raise HTTPException(status_code=403, detail="forbidden")
    elif actor.role != UserRole.Admin:
        raise HTTPException(status_code=403, detail="forbidden")


REWIND_TARGETS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.Packed: {OrderStatus.Pending},
    OrderStatus.Dispatched: {OrderStatus.Pending, OrderStatus.Packed},
}


async def rewind_order(
    *,
    session: AsyncSession,
    order: Order,
    to_status: OrderStatus,
    reason: str,
    acting_admin_id: int,
) -> Order:
    """Admin-only backward transition.

    Allowed: Packed→Pending, Dispatched→{Pending, Packed}. Terminal statuses
    (Delivered, Cancelled) reject. Reason >=10 chars required.
    """
    if order.status in (OrderStatus.Delivered, OrderStatus.Cancelled):
        raise HTTPException(status_code=409, detail={"code": "terminal_status"})
    if to_status not in REWIND_TARGETS.get(order.status, set()):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "illegal_rewind",
                "from": order.status.value,
                "to": to_status.value,
            },
        )
    if not reason or len(reason.strip()) < 10:
        raise HTTPException(
            status_code=422, detail={"code": "reason_required"}
        )

    await _assert_seller_active_for_store(session, order.store_id)

    delivery_result = await session.exec(
        select(Delivery).where(Delivery.order_id == order.id)
    )
    delivery = delivery_result.first()
    payment_result = await session.exec(
        select(Payment).where(Payment.order_id == order.id)
    )
    payment = payment_result.first()

    before = _order_snapshot(order, payment)

    order.status = to_status
    if delivery is not None:
        delivery.status = DeliveryStatus(to_status.value)
        if to_status == OrderStatus.Pending:
            delivery.packed_at = None
            delivery.dispatched_at = None
        elif to_status == OrderStatus.Packed:
            delivery.dispatched_at = None

    target_seller_id = await _resolve_seller_id_for_store(session, order.store_id)
    await audit_log(
        session=session,
        admin_user_id=acting_admin_id,
        target_seller_id=target_seller_id,
        target_type=AdminActionTargetType.Order,
        target_id=order.id,
        action="order.rewind",
        before_json=before,
        after_json=_order_snapshot(order, payment),
        reason=reason.strip(),
    )

    await session.commit()
    await session.refresh(order)
    return order


async def refund_order(
    *,
    session: AsyncSession,
    order: Order,
    reason: str,
    acting_admin_id: int,
) -> Order:
    """Admin-only refund marker.

    Preconditions:
    - Order status in ``{Cancelled, Delivered}`` (orders only refundable when
      final).
    - Payment exists and has status ``Paid``.
    - Reason >= 10 chars.

    Sets ``payment.status = Refunded`` and emits an ``order.refund`` audit row
    in the same transaction. Does NOT integrate with a real refund gateway
    (manual ledger marker for MVP).
    """
    if order.status not in (OrderStatus.Cancelled, OrderStatus.Delivered):
        raise HTTPException(
            status_code=409, detail={"code": "order_not_final"}
        )
    payment = (
        await session.exec(select(Payment).where(Payment.order_id == order.id))
    ).first()
    if payment is None or payment.status != PaymentStatus.Paid:
        raise HTTPException(
            status_code=422, detail={"code": "payment_not_refundable"}
        )
    if not reason or len(reason.strip()) < 10:
        raise HTTPException(
            status_code=422, detail={"code": "reason_required"}
        )

    await _assert_seller_active_for_store(session, order.store_id)

    before = _order_snapshot(order, payment)
    payment.status = PaymentStatus.Refunded

    target_seller_id = await _resolve_seller_id_for_store(session, order.store_id)
    await audit_log(
        session=session,
        admin_user_id=acting_admin_id,
        target_seller_id=target_seller_id,
        target_type=AdminActionTargetType.Order,
        target_id=order.id,
        action="order.refund",
        before_json=before,
        after_json=_order_snapshot(order, payment),
        reason=reason.strip(),
    )

    await session.commit()
    await session.refresh(order)
    return order


async def override_delivery_address(
    *,
    session: AsyncSession,
    order: Order,
    address_payload: AddressPayload,
    reason: str,
    acting_admin_id: int,
) -> Order:
    """Admin-only: replace the delivery address on a non-terminal order.

    1. Validate ST_DWithin between the new coordinates and the store's
       address inside the store's ``delivery_radius_km``.
    2. Insert a new ``Address`` row from the payload (preserving the
       original for audit).
    3. Update ``Order.delivery_address_id`` and rewrite the formatted
       ``delivery_address_snapshot`` string.
    4. Emit an ``order.address_override`` audit row with the *original*
       formatted snapshot in ``before_json`` (the immutable record of the
       pre-override address). See spec §10 note 3.
    """
    if order.delivery_mode == DeliveryMode.Pickup:
        raise HTTPException(
            status_code=409, detail={"detail": "not_applicable_for_pickup"}
        )
    if order.status in (OrderStatus.Delivered, OrderStatus.Cancelled):
        raise HTTPException(
            status_code=409, detail={"code": "order_not_mutable"}
        )
    if not reason or len(reason.strip()) < 10:
        raise HTTPException(
            status_code=422, detail={"code": "reason_required"}
        )

    await _assert_seller_active_for_store(session, order.store_id)

    store = await session.get(Store, order.store_id)
    if store is None:
        raise HTTPException(status_code=500, detail="store_missing")
    store_address = await session.get(Address, store.address_id)
    if store_address is None or store_address.latitude is None or store_address.longitude is None:
        raise HTTPException(status_code=409, detail={"code": "store_geo_missing"})
    if address_payload.latitude is None or address_payload.longitude is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "delivery_geo_missing"},
        )

    radius_m = (store.delivery_radius_km or 5.0) * 1000.0
    within_stmt = text(
        "SELECT ST_DWithin("
        " ST_SetSRID(ST_MakePoint(:slng, :slat), 4326)::geography,"
        " ST_SetSRID(ST_MakePoint(:nlng, :nlat), 4326)::geography,"
        " :radius) AS within"
    )
    result = await session.execute(
        within_stmt,
        {
            "slng": store_address.longitude,
            "slat": store_address.latitude,
            "nlng": address_payload.longitude,
            "nlat": address_payload.latitude,
            "radius": radius_m,
        },
    )
    if not result.scalar():
        raise HTTPException(
            status_code=422, detail={"code": "delivery_out_of_radius"}
        )

    # Preserve original snapshot for the audit row.
    before_snapshot = order.delivery_address_snapshot

    new_address = Address(**address_from_payload(address_payload))
    session.add(new_address)
    await session.flush()  # materialise new_address.id

    order.delivery_address_id = new_address.id
    order.delivery_address_snapshot = format_address(address_payload)

    target_seller_id = await _resolve_seller_id_for_store(session, order.store_id)
    await audit_log(
        session=session,
        admin_user_id=acting_admin_id,
        target_seller_id=target_seller_id,
        target_type=AdminActionTargetType.Order,
        target_id=order.id,
        action="order.address_override",
        before_json={"delivery_address_snapshot": before_snapshot},
        after_json={"delivery_address_snapshot": order.delivery_address_snapshot},
        reason=reason.strip(),
    )

    await session.commit()
    await session.refresh(order)
    return order


async def cancel_order(
    session: AsyncSession,
    order: Order,
    actor: User,
    *,
    reason: Optional[str] = None,
) -> Order:
    if order.status in (OrderStatus.Delivered, OrderStatus.Cancelled):
        raise HTTPException(status_code=409, detail="terminal_status")

    await _authorize_cancel(session, actor, order)

    acting_admin_id = actor.id if actor.role == UserRole.Admin else None

    # Admin cancelling a non-Pending order must supply a reason >= 10 chars.
    if acting_admin_id is not None:
        await _assert_seller_active_for_store(session, order.store_id)
        if order.status != OrderStatus.Pending:
            if not reason or len(reason.strip()) < 10:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "reason_required"},
                )

    delivery_result = await session.exec(select(Delivery).where(Delivery.order_id == order.id))
    delivery = delivery_result.first()
    payment_result = await session.exec(select(Payment).where(Payment.order_id == order.id))
    payment = payment_result.first()

    before = _order_snapshot(order, payment)

    order.status = OrderStatus.Cancelled
    if delivery is not None:
        delivery.status = DeliveryStatus.Cancelled
    # NOTE: dormant today — Delivered is terminal so Paid orders cannot reach
    # cancel. If a future workflow lets admins cancel post-Delivered, audit
    # this branch (real money refund, not just bookkeeping).
    if payment is not None and payment.status == PaymentStatus.Paid:
        payment.status = PaymentStatus.Refunded

    items_result = await session.exec(select(OrderItem).where(OrderItem.order_id == order.id))
    items = list(items_result.all())
    inv_ids = [item.inventory_id for item in items if item.inventory_id is not None]
    locked_inv = await lock_inventory_rows(session, inv_ids)
    inv_by_id = {inv.id: inv for inv in locked_inv}
    for item in items:
        if item.inventory_id is None:
            continue
        inv = inv_by_id.get(item.inventory_id)
        if inv is not None:
            restock(inv, item.quantity)

    # Reverse the credit charge for a cancelled credit order: decrement the
    # customer's outstanding balance + append a reversal ledger entry.
    if payment is not None and payment.method == PaymentMethod.Credit:
        from app.services import credit as credit_svc

        assert order.id is not None
        await credit_svc.reverse_credit_charge(
            session,
            store_id=order.store_id,
            customer_profile_id=order.customer_profile_id,
            order_id=order.id,
            amount=order.total,
        )

    if acting_admin_id is not None:
        target_seller_id = await _resolve_seller_id_for_store(session, order.store_id)
        await audit_log(
            session=session,
            admin_user_id=acting_admin_id,
            target_seller_id=target_seller_id,
            target_type=AdminActionTargetType.Order,
            target_id=order.id,
            action="order.cancel",
            before_json=before,
            after_json=_order_snapshot(order, payment),
            reason=(reason or "").strip() or None,
        )

    await session.commit()
    await session.refresh(order)
    return order


async def resend_delivery_otp(session: AsyncSession, order: Order) -> str:
    """Reset attempts, bump sent_at, return the existing code for re-dispatch.

    Caller must have verified the order belongs to the requesting customer.
    """
    if order.status != OrderStatus.Dispatched:
        raise HTTPException(status_code=409, detail={"code": "not_dispatched"})
    delivery = (
        await session.exec(select(Delivery).where(Delivery.order_id == order.id))
    ).first()
    if delivery is None or delivery.delivery_otp is None:
        raise HTTPException(
            status_code=409, detail={"code": "delivery_otp_not_issued"}
        )
    now = datetime.now(timezone.utc)
    if delivery.delivery_otp_sent_at is not None:
        elapsed = (now - delivery.delivery_otp_sent_at).total_seconds()
        if elapsed < settings.DELIVERY_OTP_RESEND_COOLDOWN:
            retry_after = int(settings.DELIVERY_OTP_RESEND_COOLDOWN - elapsed)
            raise HTTPException(
                status_code=429,
                detail={"code": "resend_cooldown", "retry_after": retry_after},
            )
    delivery.delivery_otp_attempts = 0
    delivery.delivery_otp_sent_at = now
    code = delivery.delivery_otp
    await session.commit()
    # commit() expired `order`; refresh so the caller's fan-out can read its
    # attributes without triggering a lazy load (→ MissingGreenlet).
    await session.refresh(order)
    return code
