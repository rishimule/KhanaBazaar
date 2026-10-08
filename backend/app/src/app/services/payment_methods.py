# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""How customers can pay a store (spec 2026-10-07).

The single home of the payment-method rules: which switches are live, which
methods each delivery mode offers, the "keep one way to pay" guard, and the
payee each order is paid to. The store API, checkout, courier, the payment
settings endpoints and the order email all ask this module.

Payee generations: `SellerProfile.upi_generation` and
`bank_transfer_generation` go up by one every time that method is switched
off, wherever that happens (`set_upi_enabled` / `set_bank_transfer_enabled`
are the only writers). An order saves the generation it was placed under; a
different generation later means the seller switched the method off since, so
the saved details may belong to a stolen or closed account and are never shown
again — the order falls back to the store's current details. A counter, not a
timestamp: no clock skew or commit-order race can make an old copy look new.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import DeliveryMode, Payment, PaymentMethod
from app.models.profile import SellerProfile, SellerProfileService
from app.models.store import Store

# Store methods each delivery mode can offer, in display order. Credit is a
# per-customer entitlement (services/credit.py), never a store switch.
MODE_METHODS: dict[DeliveryMode, tuple[PaymentMethod, ...]] = {
    DeliveryMode.DoorDelivery: (PaymentMethod.Upi, PaymentMethod.NetBanking, PaymentMethod.Cash),
    DeliveryMode.Pickup: (PaymentMethod.Upi, PaymentMethod.NetBanking, PaymentMethod.PayAtStore),
    DeliveryMode.Courier: (PaymentMethod.Upi, PaymentMethod.NetBanking),
}

# The 409 a checkout gets when the store has switched the method off.
UNAVAILABLE_CODE: dict[PaymentMethod, str] = {
    PaymentMethod.Upi: "upi_unavailable",
    PaymentMethod.NetBanking: "bank_transfer_unavailable",
    PaymentMethod.Cash: "cash_unavailable",
    PaymentMethod.PayAtStore: "pay_at_store_unavailable",
}

_ACCEPTED_ORDER = (
    PaymentMethod.Upi, PaymentMethod.NetBanking, PaymentMethod.Cash, PaymentMethod.PayAtStore,
)


def upi_live(seller: SellerProfile) -> bool:
    """UPI counts only when switched on with a payee to pay."""
    return bool(seller.upi_enabled and seller.upi_vpa)


def bank_details_complete(seller: SellerProfile) -> bool:
    return bool(seller.bank_account_name and seller.bank_account_number and seller.bank_ifsc)


def bank_transfer_live(seller: SellerProfile) -> bool:
    """Bank transfer counts only when switched on AND fully specified."""
    return bool(seller.bank_transfer_enabled) and bank_details_complete(seller)


def method_live(seller: SellerProfile, method: PaymentMethod) -> bool:
    if method is PaymentMethod.Upi:
        return upi_live(seller)
    if method is PaymentMethod.NetBanking:
        return bank_transfer_live(seller)
    if method is PaymentMethod.Cash:
        return bool(seller.cod_enabled)
    if method is PaymentMethod.PayAtStore:
        return bool(seller.pay_at_store_enabled)
    return False


def methods_for(seller: SellerProfile, mode: DeliveryMode) -> list[PaymentMethod]:
    """The store methods a customer can use for `mode` right now."""
    return [m for m in MODE_METHODS[mode] if method_live(seller, m)]


def store_accepted_methods(seller: SellerProfile) -> list[PaymentMethod]:
    """`StoreRead.accepted_payment_methods`: every live door/pickup method.
    Clients intersect it with the delivery mode."""
    return [m for m in _ACCEPTED_ORDER if method_live(seller, m)]


# ── Switch writers ──────────────────────────────────────────────────────────


def set_upi_enabled(seller: SellerProfile, enabled: bool) -> None:
    """The only writer of `upi_enabled`: an on→off move bumps the generation."""
    if seller.upi_enabled and not enabled:
        seller.upi_generation = (seller.upi_generation or 0) + 1
    seller.upi_enabled = enabled


def set_bank_transfer_enabled(seller: SellerProfile, enabled: bool) -> None:
    """The only writer of `bank_transfer_enabled`; same generation rule."""
    if seller.bank_transfer_enabled and not enabled:
        seller.bank_transfer_generation = (seller.bank_transfer_generation or 0) + 1
    seller.bank_transfer_enabled = enabled


@dataclass(frozen=True)
class MethodSwitches:
    """A switch request; None leaves that switch as it is."""

    upi_enabled: Optional[bool] = None
    bank_transfer_enabled: Optional[bool] = None
    cod_enabled: Optional[bool] = None
    pay_at_store_enabled: Optional[bool] = None


def switch_state(seller: SellerProfile) -> dict[str, bool]:
    """The four switches, for audit before/after snapshots."""
    return {
        "upi_enabled": bool(seller.upi_enabled),
        "bank_transfer_enabled": bool(seller.bank_transfer_enabled),
        "cod_enabled": bool(seller.cod_enabled),
        "pay_at_store_enabled": bool(seller.pay_at_store_enabled),
    }


async def pickup_offered(session: AsyncSession, seller_profile_id: int) -> bool:
    """Whether any of the seller's services takes pickup orders."""
    row = (
        await session.exec(
            select(SellerProfileService.id)
            .where(
                SellerProfileService.seller_profile_id == seller_profile_id,
                SellerProfileService.pickup_enabled == True,  # noqa: E712
            )
            .limit(1)
        )
    ).first()
    return row is not None


async def courier_offered(session: AsyncSession, seller_profile_id: int) -> bool:
    """A courier ring is set and at least one service ships by courier —
    regardless of payees, so the settings page can warn when nothing can pay."""
    radius = (
        await session.exec(
            select(Store.courier_radius_km).where(Store.seller_profile_id == seller_profile_id)
        )
    ).first()
    if radius is None:
        return False
    row = (
        await session.exec(
            select(SellerProfileService.id)
            .where(
                SellerProfileService.seller_profile_id == seller_profile_id,
                SellerProfileService.courier_enabled == True,  # noqa: E712
            )
            .limit(1)
        )
    ).first()
    return row is not None


async def apply_method_switches(
    session: AsyncSession,
    seller: SellerProfile,
    switches: MethodSwitches,
    *,
    seller_active: bool,
) -> None:
    """Apply a switch request to a seller row the caller has locked. Every
    check runs before anything is written; the caller commits.

    Turning a method on needs an active seller and approved details. Turning
    one off always works, except that cash on delivery and pay at store may not
    leave a delivery mode the store offers with no way to pay. UPI and bank
    transfer are emergency stops for a stolen or closed account, so they are
    never refused (spec D5).
    """
    requested = (
        ("upi_enabled", switches.upi_enabled),
        ("bank_transfer_enabled", switches.bank_transfer_enabled),
        ("cod_enabled", switches.cod_enabled),
        ("pay_at_store_enabled", switches.pay_at_store_enabled),
    )
    if not seller_active and any(
        value is True and not getattr(seller, name) for name, value in requested
    ):
        raise HTTPException(status_code=409, detail="seller_not_active")
    if switches.upi_enabled is True and not seller.upi_vpa:
        raise HTTPException(status_code=409, detail="upi_payee_missing")
    if switches.bank_transfer_enabled is True and not bank_details_complete(seller):
        raise HTTPException(status_code=409, detail="bank_transfer_incomplete")

    # The guard looks at the state the request would leave behind.
    upi_after = (
        upi_live(seller) if switches.upi_enabled is None
        else switches.upi_enabled and bool(seller.upi_vpa)
    )
    bank_after = (
        bank_transfer_live(seller) if switches.bank_transfer_enabled is None
        else switches.bank_transfer_enabled and bank_details_complete(seller)
    )
    if (
        switches.cod_enabled is False
        and seller.cod_enabled
        and not (upi_after or bank_after)
    ):
        raise HTTPException(
            status_code=409, detail={"code": "last_payment_method", "mode": "door_delivery"}
        )
    if (
        switches.pay_at_store_enabled is False
        and seller.pay_at_store_enabled
        and not (upi_after or bank_after)
        and seller.id is not None
        and await pickup_offered(session, seller.id)
    ):
        raise HTTPException(
            status_code=409, detail={"code": "last_payment_method", "mode": "pickup"}
        )

    if switches.upi_enabled is not None:
        set_upi_enabled(seller, switches.upi_enabled)
    if switches.bank_transfer_enabled is not None:
        set_bank_transfer_enabled(seller, switches.bank_transfer_enabled)
    if switches.cod_enabled is not None:
        seller.cod_enabled = switches.cod_enabled
    if switches.pay_at_store_enabled is not None:
        seller.pay_at_store_enabled = switches.pay_at_store_enabled
    session.add(seller)


# ── Payee saved per order ───────────────────────────────────────────────────


@dataclass(frozen=True)
class UpiPayee:
    vpa: str
    display_name: str


@dataclass(frozen=True)
class BankPayee:
    account_name: str
    account_number: str
    ifsc: str


def snapshot_payee(
    payment: Payment, seller: SellerProfile, *, mode: DeliveryMode, method: PaymentMethod
) -> None:
    """Copy the payee(s) this order can be paid to onto its payment row.

    Local UPI / bank orders save the chosen method; courier orders save every
    live prepaid method, because the customer may switch method after accepting
    the quote. Cash, pay at store and credit need no payee.
    """
    if mode is DeliveryMode.Courier:
        wanted: tuple[PaymentMethod, ...] = (PaymentMethod.Upi, PaymentMethod.NetBanking)
    elif method in (PaymentMethod.Upi, PaymentMethod.NetBanking):
        wanted = (method,)
    else:
        return
    if PaymentMethod.Upi in wanted and upi_live(seller):
        payment.payee_upi_vpa = seller.upi_vpa
        payment.payee_upi_name = seller.business_name
        payment.payee_upi_generation = seller.upi_generation
    if PaymentMethod.NetBanking in wanted and bank_transfer_live(seller):
        payment.payee_bank_account_name = seller.bank_account_name
        payment.payee_bank_account_number = seller.bank_account_number
        payment.payee_bank_ifsc = seller.bank_ifsc
        payment.payee_bank_generation = seller.bank_transfer_generation


def effective_upi(payment: Optional[Payment], seller: SellerProfile) -> Optional[UpiPayee]:
    """The UPI payee an unpaid order shows (spec §7): None while UPI is off;
    the saved copy while its generation still matches; otherwise the current
    approved one (switched off since placement, or nothing saved)."""
    if not upi_live(seller):
        return None
    if (
        payment is not None
        and payment.payee_upi_vpa
        and payment.payee_upi_generation == seller.upi_generation
    ):
        return UpiPayee(payment.payee_upi_vpa, payment.payee_upi_name or seller.business_name)
    return UpiPayee(seller.upi_vpa or "", seller.business_name)


def effective_bank(payment: Optional[Payment], seller: SellerProfile) -> Optional[BankPayee]:
    """Bank-transfer twin of `effective_upi`."""
    if not bank_transfer_live(seller):
        return None
    if (
        payment is not None
        and payment.payee_bank_account_number
        and payment.payee_bank_generation == seller.bank_transfer_generation
    ):
        return BankPayee(
            payment.payee_bank_account_name or "",
            payment.payee_bank_account_number,
            payment.payee_bank_ifsc or "",
        )
    return BankPayee(
        seller.bank_account_name or "", seller.bank_account_number or "", seller.bank_ifsc or ""
    )


def saved_upi(payment: Payment) -> Optional[UpiPayee]:
    """The UPI payee as copied at placement — the admin dispute record."""
    if not payment.payee_upi_vpa:
        return None
    return UpiPayee(payment.payee_upi_vpa, payment.payee_upi_name or "")


def saved_bank(payment: Payment) -> Optional[BankPayee]:
    if not payment.payee_bank_account_number:
        return None
    return BankPayee(
        payment.payee_bank_account_name or "",
        payment.payee_bank_account_number,
        payment.payee_bank_ifsc or "",
    )


async def seller_for_store(session: AsyncSession, store_id: int) -> Optional[SellerProfile]:
    return (
        await session.exec(
            select(SellerProfile)
            .join(Store, Store.seller_profile_id == SellerProfile.id)  # type: ignore[arg-type]
            .where(Store.id == store_id)
        )
    ).first()
