import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.dev_seed import (
    get_canonical_login_email_rows,
    get_seller_application_subset_login_email_rows,
    get_seed_counts,
    seed_demo_data,
    seed_seller_application_subset,
)
from app.models.base import User
from app.models.seller import SellerProfile, VerificationStatus

CANONICAL_FULL_COUNTS = {
    "users": 8,
    "sellerprofile": 6,
    "category": 4,
    "masterproduct": 12,
    "store": 3,
    "storeinventory": 26,
}

SELLER_APPLICATION_SUBSET_COUNTS = {
    "users": 4,
    "sellerprofile": 3,
    "category": 0,
    "masterproduct": 0,
    "store": 0,
    "storeinventory": 0,
}


def test_seed_login_email_helpers_expose_stable_rows() -> None:
    assert get_canonical_login_email_rows() == [
        ("admin", "admin@khanabazaar.dev"),
        ("seller", "seller@khanabazaar.dev"),
        ("seller", "seller2@khanabazaar.dev"),
        ("seller", "seller3@khanabazaar.dev"),
        ("customer", "customer@khanabazaar.dev"),
        ("seller", "pending.seller@khanabazaar.dev"),
        ("seller", "approved.seller@khanabazaar.dev"),
        ("seller", "rejected.seller@khanabazaar.dev"),
    ]
    assert get_seller_application_subset_login_email_rows() == [
        ("admin", "admin@khanabazaar.dev"),
        ("seller", "pending.seller@khanabazaar.dev"),
        ("seller", "approved.seller@khanabazaar.dev"),
        ("seller", "rejected.seller@khanabazaar.dev"),
    ]


@pytest.mark.asyncio
async def test_seed_demo_data_populates_canonical_counts(session: AsyncSession) -> None:
    await seed_demo_data(session)

    counts = await get_seed_counts(session)

    assert counts == CANONICAL_FULL_COUNTS


@pytest.mark.asyncio
async def test_seed_demo_data_is_idempotent(session: AsyncSession) -> None:
    await seed_demo_data(session)
    await seed_demo_data(session)

    counts = await get_seed_counts(session)

    assert counts == CANONICAL_FULL_COUNTS


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

    assert counts == SELLER_APPLICATION_SUBSET_COUNTS
    assert statuses == {
        "approved.seller@khanabazaar.dev": VerificationStatus.Approved,
        "pending.seller@khanabazaar.dev": VerificationStatus.Pending,
        "rejected.seller@khanabazaar.dev": VerificationStatus.Rejected,
    }
