# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.seller_onboarding_request import (
    OnboardingRequestStatus,
    SellerOnboardingRequest,
)


@pytest.mark.asyncio
async def test_seller_onboarding_request_persists_with_defaults(session: AsyncSession):
    row = SellerOnboardingRequest(
        store_name="Sharma Kirana",
        contact_phone="+919812345678",
        contact_email="sharma@example.com",
        contact_address="12 MG Road, Pune 411001",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    assert row.id is not None
    assert row.created_at is not None
    assert row.status == OnboardingRequestStatus.new
    assert row.preferred_categories is None
    assert row.area_lat is None
    assert row.submitted_by_user_id is None
