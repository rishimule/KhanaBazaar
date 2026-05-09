# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Tests for the one-shot backfill Celery task that forward-geocodes
store + business addresses missing lat/lng. Customer-only addresses must
NOT be touched."""
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import worker as worker_module
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    VerificationStatus,
)
from app.models.store import Store


@pytest.mark.asyncio
async def test_backfill_only_touches_store_and_business_addresses(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Customer-only address (NOT linked via Store or business_address).
    customer_user = User(
        id=801, email="cust@kb.com", role=UserRole.Customer, is_active=True,
    )
    session.add(customer_user)
    await session.flush()
    cust_profile = CustomerProfile(user_id=customer_user.id, first_name="C")
    session.add(cust_profile)
    await session.flush()
    cust_addr = Address(
        address_line1="Cust Only", city="Mumbai", state="Maharashtra",
        pincode="400001", country="India",
    )
    session.add(cust_addr)
    await session.flush()
    session.add(CustomerAddress(
        customer_profile_id=cust_profile.id, address_id=cust_addr.id,
        is_default=True,
    ))

    # Seller business + store address, both NULL lat/lng.
    seller_user = User(
        id=802, email="sel@kb.com", role=UserRole.Seller, is_active=True,
    )
    session.add(seller_user)
    await session.flush()
    biz_addr = Address(
        address_line1="Biz", city="Mumbai", state="Maharashtra",
        pincode="400002", country="India",
    )
    session.add(biz_addr)
    await session.flush()
    seller_profile = SellerProfile(
        user_id=seller_user.id, first_name="S", business_name="S",
        phone="+919811119999",
        bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_addr.id,
    )
    session.add(seller_profile)
    await session.flush()
    store_addr = Address(
        address_line1="Store", city="Mumbai", state="Maharashtra",
        pincode="400003", country="India",
    )
    session.add(store_addr)
    await session.flush()
    session.add(Store(
        name="Test Store", seller_profile_id=seller_profile.id,
        address_id=store_addr.id, delivery_radius_km=5.0,
        is_active=True, pin_confirmed=False,
    ))
    cust_addr_id = cust_addr.id
    biz_addr_id = biz_addr.id
    store_addr_id = store_addr.id
    await session.commit()

    # Stub the google forward-geocoder.
    async def fake(query: str) -> tuple[float, float] | None:
        return (18.9220, 72.8347)

    monkeypatch.setattr(worker_module, "_forward_geocode_one", fake)
    # Backfill task creates its own engine via settings.DATABASE_URL — point
    # it at the test DB so we don't write to the dev database.
    from app.core.config import settings
    monkeypatch.setattr(
        settings, "DATABASE_URL",
        "postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar_test",
    )

    result = worker_module.backfill_store_addresses_geocode.delay().get()
    assert result["filled"] == 2  # biz + store
    assert result["skipped"] == 0

    # Refresh the in-memory objects from the DB to see the writes.
    cust_after = await session.get(Address, cust_addr_id)
    biz_after = await session.get(Address, biz_addr_id)
    store_after = await session.get(Address, store_addr_id)
    assert cust_after is not None
    assert biz_after is not None
    assert store_after is not None
    assert cust_after.latitude is None  # customer-only NOT touched
    assert cust_after.digipin is None
    assert biz_after.latitude == 18.9220
    assert biz_after.longitude == 72.8347
    assert biz_after.digipin is not None
    assert store_after.latitude == 18.9220
    assert store_after.digipin is not None


@pytest.mark.asyncio
async def test_backfill_low_confidence_result_skipped(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seller_user = User(
        id=803, email="sel2@kb.com", role=UserRole.Seller, is_active=True,
    )
    session.add(seller_user)
    await session.flush()
    biz_addr = Address(
        address_line1="Biz2", city="Mumbai", state="Maharashtra",
        pincode="400004", country="India",
    )
    session.add(biz_addr)
    await session.flush()
    session.add(SellerProfile(
        user_id=seller_user.id, first_name="S2", business_name="S2",
        phone="+919811118888",
        bank_account_number="2", bank_ifsc="HDFC0000002",
        verification_status=VerificationStatus.Approved,
        business_address_id=biz_addr.id,
    ))
    biz_addr_id = biz_addr.id
    await session.commit()

    async def fake_returns_none(query: str) -> tuple[float, float] | None:
        return None

    monkeypatch.setattr(worker_module, "_forward_geocode_one", fake_returns_none)
    from app.core.config import settings
    monkeypatch.setattr(
        settings, "DATABASE_URL",
        "postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar_test",
    )

    result = worker_module.backfill_store_addresses_geocode.delay().get()
    assert result["filled"] == 0
    assert result["skipped"] == 1

    after = await session.get(Address, biz_addr_id)
    assert after is not None
    assert after.latitude is None
