import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.dev_seed import (
    EXPECTED_COUNTS,
    get_seed_counts,
    seed_demo_data,
    seed_seller_application_subset,
)
from app.models.base import User
from app.models.seller import SellerProfile, VerificationStatus


@pytest.mark.asyncio
async def test_seed_demo_data_populates_canonical_counts(session: AsyncSession) -> None:
    await seed_demo_data(session)

    counts = await get_seed_counts(session)

    assert counts == EXPECTED_COUNTS


@pytest.mark.asyncio
async def test_seed_demo_data_is_idempotent(session: AsyncSession) -> None:
    await seed_demo_data(session)
    await seed_demo_data(session)

    counts = await get_seed_counts(session)

    assert counts == EXPECTED_COUNTS


@pytest.mark.asyncio
async def test_seed_demo_data_creates_expected_seller_statuses(session: AsyncSession) -> None:
    await seed_demo_data(session)

    result = await session.exec(select(User, SellerProfile).join(SellerProfile))
    seller_rows = result.all()

    statuses = {
        user.email: seller_profile.verification_status
        for user, seller_profile in seller_rows
    }

    assert statuses == {
        "approved.seller@khanabazaar.dev": VerificationStatus.Approved,
        "pending.seller@khanabazaar.dev": VerificationStatus.Pending,
        "rejected.seller@khanabazaar.dev": VerificationStatus.Rejected,
        "seller2@khanabazaar.dev": VerificationStatus.Approved,
        "seller3@khanabazaar.dev": VerificationStatus.Approved,
        "seller@khanabazaar.dev": VerificationStatus.Approved,
    }


@pytest.mark.asyncio
async def test_seed_seller_application_subset_creates_only_review_rows(
    session: AsyncSession,
) -> None:
    await seed_seller_application_subset(session)

    counts = await get_seed_counts(session)
    result = await session.exec(select(User, SellerProfile).join(SellerProfile))
    seller_rows = result.all()

    statuses = {
        user.email: seller_profile.verification_status
        for user, seller_profile in seller_rows
    }

    assert counts["users"] == 4
    assert counts["sellerprofile"] == 3
    assert counts["category"] == 0
    assert counts["masterproduct"] == 0
    assert counts["store"] == 0
    assert counts["storeinventory"] == 0
    assert statuses == {
        "approved.seller@khanabazaar.dev": VerificationStatus.Approved,
        "pending.seller@khanabazaar.dev": VerificationStatus.Pending,
        "rejected.seller@khanabazaar.dev": VerificationStatus.Rejected,
    }
