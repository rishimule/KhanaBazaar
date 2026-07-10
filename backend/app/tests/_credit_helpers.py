# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Shared factories for the credit-customer test suite."""
import uuid
from typing import Any, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User, UserRole
from app.models.credit import SellerCreditConfig
from app.models.profile import CustomerProfile


async def make_customer(
    session: AsyncSession,
    *,
    email: Optional[str] = None,
    phone: Optional[str] = None,
) -> dict[str, Any]:
    user = User(
        email=email or f"c-{uuid.uuid4().hex[:8]}@x.test", role=UserRole.Customer
    )
    session.add(user)
    await session.flush()
    prof = CustomerProfile(
        user_id=user.id, first_name="Cust", last_name="Omer", phone=phone
    )
    session.add(prof)
    await session.commit()
    await session.refresh(prof)
    await session.refresh(user)
    return {"user": user, "profile": prof}


async def enable_credit(
    session: AsyncSession,
    seller_profile_id: int,
    *,
    max_limit_per_customer: float = 10000.0,
) -> SellerCreditConfig:
    cfg = SellerCreditConfig(
        seller_profile_id=seller_profile_id,
        credit_enabled=True,
        max_limit_per_customer=max_limit_per_customer,
    )
    session.add(cfg)
    await session.commit()
    await session.refresh(cfg)
    return cfg
