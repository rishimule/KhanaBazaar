# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Seller payment settings (spec 2026-10-07 §4, §8).

The four method switches take effect at once; the payee details behind UPI
and bank transfer are reviewed through the `payments` / `banking` change
requests (api/seller_change_requests.py). Every rule lives in
services/payment_methods.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin, get_current_seller
from app.db.session import get_db_session
from app.models.admin_audit import AdminActionTargetType
from app.models.base import User
from app.models.commerce import DeliveryMode
from app.models.profile import SellerProfile, VerificationStatus
from app.schemas.seller_payments import (
    AdminPaymentMethodsUpdate,
    PaymentMethodsUpdate,
    PaymentSettingsRead,
)
from app.services import admin_audit
from app.services.payment_methods import (
    MethodSwitches,
    apply_method_switches,
    bank_details_complete,
    bank_transfer_live,
    courier_offered,
    methods_for,
    pickup_offered,
    switch_state,
    upi_live,
)

router = APIRouter()


async def _profile_for_user(
    session: AsyncSession, user_id: int, *, lock: bool = False
) -> SellerProfile:
    stmt = select(SellerProfile).where(SellerProfile.user_id == user_id)
    if lock:
        # Serialise switch requests so the guard reads what it is guarding.
        stmt = stmt.with_for_update()
    profile = (await session.exec(stmt)).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="seller_not_found")
    return profile


async def _settings(session: AsyncSession, profile: SellerProfile) -> PaymentSettingsRead:
    assert profile.id is not None
    pickup = await pickup_offered(session, profile.id)
    courier = await courier_offered(session, profile.id)
    by_mode = {DeliveryMode.DoorDelivery.value: methods_for(profile, DeliveryMode.DoorDelivery)}
    if pickup:
        by_mode[DeliveryMode.Pickup.value] = methods_for(profile, DeliveryMode.Pickup)
    if courier:
        by_mode[DeliveryMode.Courier.value] = methods_for(profile, DeliveryMode.Courier)
    return PaymentSettingsRead(
        upi_enabled=profile.upi_enabled,
        upi_vpa=profile.upi_vpa,
        upi_live=upi_live(profile),
        bank_transfer_enabled=profile.bank_transfer_enabled,
        bank_account_name=profile.bank_account_name,
        bank_account_number=profile.bank_account_number,
        bank_ifsc=profile.bank_ifsc,
        bank_details_complete=bank_details_complete(profile),
        bank_transfer_live=bank_transfer_live(profile),
        cod_enabled=profile.cod_enabled,
        pay_at_store_enabled=profile.pay_at_store_enabled,
        pickup_offered=pickup,
        courier_offered=courier,
        methods_by_mode=by_mode,
    )


def _switches(body: PaymentMethodsUpdate) -> MethodSwitches:
    return MethodSwitches(
        upi_enabled=body.upi_enabled,
        bank_transfer_enabled=body.bank_transfer_enabled,
        cod_enabled=body.cod_enabled,
        pay_at_store_enabled=body.pay_at_store_enabled,
    )


def _is_active(profile: SellerProfile) -> bool:
    return profile.verification_status is VerificationStatus.Approved


@router.get("/me/payments", response_model=PaymentSettingsRead)
async def get_my_payment_settings(
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> PaymentSettingsRead:
    assert seller.id is not None
    return await _settings(session, await _profile_for_user(session, seller.id))


@router.patch("/me/payments/methods", response_model=PaymentSettingsRead)
async def set_my_payment_methods(
    body: PaymentMethodsUpdate,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> PaymentSettingsRead:
    """Flip the seller's own switches. Instant — switching a method on reuses
    details an admin already approved; switching one off only removes an
    option. Returns the full settings so every open tab can re-sync."""
    assert seller.id is not None
    profile = await _profile_for_user(session, seller.id, lock=True)
    await apply_method_switches(
        session, profile, _switches(body), seller_active=_is_active(profile)
    )
    await session.commit()
    await session.refresh(profile)
    return await _settings(session, profile)


@router.get("/admin/{seller_id}/payments", response_model=PaymentSettingsRead)
async def admin_get_payment_settings(
    seller_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PaymentSettingsRead:
    """`seller_id` is the seller's User.id, like the other admin seller routes."""
    return await _settings(session, await _profile_for_user(session, seller_id))


@router.patch("/admin/{seller_id}/payments/methods", response_model=PaymentSettingsRead)
async def admin_set_payment_methods(
    seller_id: int,
    body: AdminPaymentMethodsUpdate,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PaymentSettingsRead:
    """An admin flips a seller's switches — e.g. stops a stolen UPI ID when the
    seller can't. Same rules as the seller's own switches: switching off works
    for any seller status, switching on needs an approved seller. Audited in
    the same transaction as the change."""
    assert admin.id is not None
    reason = (body.reason or "").strip()
    if len(reason) < 10:
        raise HTTPException(status_code=422, detail={"code": "reason_required"})
    profile = await _profile_for_user(session, seller_id, lock=True)
    assert profile.id is not None
    before = switch_state(profile)
    await apply_method_switches(
        session, profile, _switches(body), seller_active=_is_active(profile)
    )
    after = switch_state(profile)
    if after != before:
        await admin_audit.log(
            session=session,
            admin_user_id=admin.id,
            target_seller_id=profile.id,
            target_type=AdminActionTargetType.SellerProfile,
            target_id=profile.id,
            action="payments.set_methods",
            before_json=before,
            after_json=after,
            reason=reason,
        )
    await session.commit()
    await session.refresh(profile)
    return await _settings(session, profile)
