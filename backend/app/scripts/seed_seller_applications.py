#!/usr/bin/env python3
"""
Seed seller applications for the admin approval workflow walkthrough.

Creates three seller users (pending, approved, rejected) along with their
SellerProfile rows. Also ensures an admin user exists. Idempotent.

Usage (from backend/app/):
    uv run python scripts/seed_seller_applications.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.base import User, UserRole
from app.models.seller import SellerProfile, VerificationStatus

ADMIN = {
    "email": "admin@khanabazaar.dev",
    "full_name": "Platform Admin",
    "role": UserRole.Admin,
}

APPLICATIONS = [
    {
        "email": "pending.seller@khanabazaar.dev",
        "full_name": "Arjun Menon",
        "business_name": "Arjun Fresh Kirana",
        "business_category": "Groceries",
        "address_line1": "221B, Carter Road",
        "address_line2": "Bandra West",
        "landmark": "Near Bandstand Promenade",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400050",
        "country": "India",
        "latitude": None,
        "longitude": None,
        "phone": "+919812345670",
        "gst_number": "27ABCDE1234F1Z5",
        "fssai_license": "11223344556677",
        "bank_account_number": "50100200300400",
        "bank_ifsc": "HDFC0001234",
        "status": VerificationStatus.Pending,
        "rejection_reason": None,
    },
    {
        "email": "approved.seller@khanabazaar.dev",
        "full_name": "Sana Kapoor",
        "business_name": "Sana Organic Mart",
        "business_category": "Organic Produce",
        "address_line1": "14, Brigade Road",
        "address_line2": "Ashok Nagar",
        "landmark": "Opposite Cauvery Emporium",
        "city": "Bengaluru",
        "state": "Karnataka",
        "pincode": "560001",
        "country": "India",
        "latitude": None,
        "longitude": None,
        "phone": "+919812345671",
        "gst_number": "29FGHIJ5678K2Z6",
        "fssai_license": "22334455667788",
        "bank_account_number": "60100200300500",
        "bank_ifsc": "ICIC0005678",
        "status": VerificationStatus.Approved,
        "rejection_reason": None,
    },
    {
        "email": "rejected.seller@khanabazaar.dev",
        "full_name": "Vikram Singh",
        "business_name": "Vikram Provision Store",
        "business_category": "Groceries",
        "address_line1": "7, Sector 18",
        "address_line2": None,
        "landmark": "Near Atta Market",
        "city": "Noida",
        "state": "Uttar Pradesh",
        "pincode": "201301",
        "country": "India",
        "latitude": None,
        "longitude": None,
        "phone": "+919812345672",
        "gst_number": "09KLMNO9012P3Z7",
        "fssai_license": "33445566778899",
        "bank_account_number": "70100200300600",
        "bank_ifsc": "SBIN0009012",
        "status": VerificationStatus.Rejected,
        "rejection_reason": "GST number does not match business address on record. Please update and resubmit.",
    },
]


_ADDRESS_KEYS = (
    "address_line1",
    "address_line2",
    "landmark",
    "city",
    "state",
    "pincode",
    "country",
    "latitude",
    "longitude",
)


async def _upsert_user(session: AsyncSession, email: str, full_name: str, role: UserRole) -> User:
    existing = await session.exec(select(User).where(User.email == email))
    user = existing.first()
    if user:
        print(f"  user exists: {email}")
        return user
    user = User(email=email, full_name=full_name, role=role, is_active=True)
    session.add(user)
    await session.flush()
    print(f"  user created: {email} (id={user.id}, role={role.value})")
    return user


async def _upsert_profile(session: AsyncSession, user: User, data: dict) -> None:
    assert user.id is not None
    existing = await session.exec(
        select(SellerProfile).where(SellerProfile.user_id == user.id)
    )
    profile = existing.first()
    if profile:
        profile.verification_status = data["status"]
        profile.rejection_reason = data["rejection_reason"]
        session.add(profile)
        print(f"  profile updated: {user.email} -> {data['status'].value}")
        return
    profile = SellerProfile(
        user_id=user.id,
        business_name=data["business_name"],
        business_category=data["business_category"],
        phone=data["phone"],
        gst_number=data["gst_number"],
        fssai_license=data["fssai_license"],
        bank_account_number=data["bank_account_number"],
        bank_ifsc=data["bank_ifsc"],
        verification_status=data["status"],
        rejection_reason=data["rejection_reason"],
        **{k: data[k] for k in _ADDRESS_KEYS},
    )
    session.add(profile)
    print(f"  profile created: {user.email} -> {data['status'].value}")


async def seed() -> None:
    print("\nSeeding seller applications...\n")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with AsyncSession(engine) as session:
        print("1  Admin user")
        await _upsert_user(session, ADMIN["email"], ADMIN["full_name"], ADMIN["role"])

        print("\n2  Seller users + profiles")
        for app in APPLICATIONS:
            user = await _upsert_user(session, app["email"], app["full_name"], UserRole.Seller)
            await _upsert_profile(session, user, app)

        await session.commit()

    await engine.dispose()

    print("\nDone.\n")
    print("Login via email OTP (check backend console for the code):")
    print(f"  admin    : {ADMIN['email']}")
    for app in APPLICATIONS:
        print(f"  seller   : {app['email']}  -> {app['status'].value}")


if __name__ == "__main__":
    asyncio.run(seed())
