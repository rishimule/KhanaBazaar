# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Seller payment settings: switches, method rules, generations and the
settings endpoints (spec 2026-10-07 §4, §5, §8)."""
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Payment
from app.models.profile import SellerProfile
from tests._courier_helpers import CourierWorld


def _profile(**fields: Any) -> SellerProfile:
    """An unsaved seller with every method live unless overridden."""
    base: dict[str, Any] = dict(
        user_id=1, first_name="Ravi", phone="+919900000002",
        business_name="Ravi Sweets", business_address_id=1,
        upi_vpa="ravi@okaxis", upi_enabled=True,
        bank_account_name="Ravi Sweets", bank_account_number="123456789012",
        bank_ifsc="HDFC0001234", bank_transfer_enabled=True,
    )
    base.update(fields)
    return SellerProfile(**base)


async def _seller(session: AsyncSession, world: CourierWorld) -> SellerProfile:
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    await session.refresh(seller)
    return seller


def test_new_switches_start_on_and_generations_at_zero() -> None:
    seller = _profile()
    assert seller.cod_enabled is True and seller.pay_at_store_enabled is True
    assert seller.upi_generation == 0 and seller.bank_transfer_generation == 0


def test_payment_carries_a_saved_payee() -> None:
    assert {
        "payee_upi_vpa", "payee_upi_name", "payee_upi_generation",
        "payee_bank_account_name", "payee_bank_account_number",
        "payee_bank_ifsc", "payee_bank_generation",
    } <= set(Payment.model_fields)
