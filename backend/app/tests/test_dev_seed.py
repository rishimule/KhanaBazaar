# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.dev_seed import (
    APPLICATIONS,
    EXPECTED_FULL_COUNTS,
    LANGUAGES,
    SERVICES,
    get_canonical_login_email_rows,
    get_seed_counts,
    get_seller_application_subset_login_email_rows,
    seed_demo_data,
    seed_seller_application_subset,
)
from app.models.address import Address
from app.models.base import User
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    VerificationStatus,
)
from app.models.store import Store

CANONICAL_FULL_COUNTS = EXPECTED_FULL_COUNTS

# Subset path seeds: 1 admin + every APPLICATION as a seller user. Each
# application also creates its own SellerProfile + SellerProfileService link
# + business Address row. SERVICES are seeded too so service_slugs resolve.
SELLER_APPLICATION_SUBSET_COUNTS = {
    **dict.fromkeys(EXPECTED_FULL_COUNTS, 0),
    "users": 1 + len(APPLICATIONS),
    "language": len(LANGUAGES),
    "adminprofile": 1,
    "sellerprofile": len(APPLICATIONS),
    "sellerprofile_service": sum(len(a["service_slugs"]) for a in APPLICATIONS),
    "address": len(APPLICATIONS),
    "service": len(SERVICES),
    "service_translation": len(SERVICES),
}

# Anchor login rows that must remain present and in stable positions even as
# the extra-data layer grows. Anchors are at the start of TEST_USERS, so
# slicing the head of `get_canonical_login_email_rows()` keeps the assertion
# resilient to extra-seller additions.
ANCHOR_LOGIN_HEAD = [
    ("admin", "admin@khanabazaar.dev"),
    ("seller", "seller@khanabazaar.dev"),
    ("seller", "seller2@khanabazaar.dev"),
    ("seller", "seller3@khanabazaar.dev"),
    ("seller", "seller4@khanabazaar.dev"),
    ("seller", "seller5@khanabazaar.dev"),
    ("seller", "seller6@khanabazaar.dev"),
    ("seller", "seller7@khanabazaar.dev"),
    ("seller", "seller8@khanabazaar.dev"),
    ("seller", "seller9@khanabazaar.dev"),
]
ANCHOR_CUSTOMER_LOGIN = ("customer", "customer@khanabazaar.dev")
ANCHOR_APPLICATION_LOGINS = [
    ("seller", "pending.seller@khanabazaar.dev"),
    ("seller", "approved.seller@khanabazaar.dev"),
    ("seller", "rejected.seller@khanabazaar.dev"),
]


def test_seed_login_email_helpers_expose_stable_rows() -> None:
    canonical = get_canonical_login_email_rows()
    # Admin + 9 anchor sellers come first.
    assert canonical[: len(ANCHOR_LOGIN_HEAD)] == ANCHOR_LOGIN_HEAD
    # Anchor customer is present and tagged correctly.
    assert ANCHOR_CUSTOMER_LOGIN in canonical
    # All 3 anchor application emails present.
    for row in ANCHOR_APPLICATION_LOGINS:
        assert row in canonical

    subset = get_seller_application_subset_login_email_rows()
    assert subset[0] == ("admin", "admin@khanabazaar.dev")
    for row in ANCHOR_APPLICATION_LOGINS:
        assert row in subset
    assert len(subset) == 1 + len(APPLICATIONS)


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

    # Anchor sellers + anchor applications retain stable statuses.
    assert statuses["seller@khanabazaar.dev"] == VerificationStatus.Approved
    for n in range(2, 10):
        assert statuses[f"seller{n}@khanabazaar.dev"] == VerificationStatus.Approved
    assert statuses["approved.seller@khanabazaar.dev"] == VerificationStatus.Approved
    assert statuses["pending.seller@khanabazaar.dev"] == VerificationStatus.Pending
    assert statuses["rejected.seller@khanabazaar.dev"] == VerificationStatus.Rejected

    # Total profiles: 9 anchor sellers + 81 extra sellers + 30 applications.
    # Anchor applications split 1/1/1 (pending/approved/rejected); extras split 9/9/9.
    counts: dict[VerificationStatus, int] = {
        VerificationStatus.Approved: 0,
        VerificationStatus.Pending: 0,
        VerificationStatus.Rejected: 0,
    }
    for status in statuses.values():
        counts[status] += 1
    # Approved = 9 anchor sellers + 81 extra sellers + (1 anchor approved app + 9 extra approved apps).
    assert counts[VerificationStatus.Approved] == 9 + 81 + 10
    assert counts[VerificationStatus.Pending] == 10
    assert counts[VerificationStatus.Rejected] == 10


@pytest.mark.asyncio
async def test_customer_has_five_addresses_with_default_home(
    session: AsyncSession,
) -> None:
    await seed_demo_data(session)

    profile = (
        await session.exec(
            select(CustomerProfile)
            .join(User, User.id == CustomerProfile.user_id)  # type: ignore[arg-type]
            .where(User.email == "customer@khanabazaar.dev")
        )
    ).first()
    assert profile is not None

    rows = (
        await session.exec(
            select(CustomerAddress, Address)
            .join(Address, Address.id == CustomerAddress.address_id)  # type: ignore[arg-type]
            .where(CustomerAddress.customer_profile_id == profile.id)
        )
    ).all()
    assert len(rows) == 5

    labels = sorted(ca.label or "" for ca, _ in rows)
    assert labels == ["Friend's Place", "Home", "Office", "Parents", "Pune Trip"]

    defaults = [ca for ca, _ in rows if ca.is_default]
    assert len(defaults) == 1
    assert defaults[0].label == "Home"

    for _, addr in rows:
        assert addr.latitude is not None
        assert addr.longitude is not None
        assert addr.digipin is not None
        assert addr.place_id is not None


@pytest.mark.asyncio
async def test_all_seeded_stores_in_mumbai_with_pin_confirmed(
    session: AsyncSession,
) -> None:
    await seed_demo_data(session)

    rows = (
        await session.exec(
            select(Store, Address).join(Address, Address.id == Store.address_id)  # type: ignore[arg-type]
        )
    ).all()
    assert len(rows) == EXPECTED_FULL_COUNTS["store"]

    for store, addr in rows:
        assert store.pin_confirmed is True
        assert 0.5 <= store.delivery_radius_km <= 50.0
        assert addr.latitude is not None and addr.longitude is not None
        # Mumbai metro bbox (loose): lat ~18.85–19.30, lng ~72.75–73.00.
        # Generated stores draw from MUMBAI_NEIGHBORHOODS which sit inside this box.
        assert 18.85 < addr.latitude < 19.30, f"{store.name}: lat {addr.latitude}"
        assert 72.75 < addr.longitude < 73.00, f"{store.name}: lng {addr.longitude}"
        assert addr.digipin is not None


@pytest.mark.asyncio
async def test_bandra_home_is_serviceable_for_sharma_store(
    session: AsyncSession,
) -> None:
    await seed_demo_data(session)
    sql = text(
        "SELECT EXISTS ("
        "  SELECT 1 FROM customeraddress ca "
        "  JOIN address ha ON ha.id = ca.address_id "
        "  JOIN store s ON s.name = 'Sharma General Store' "
        "  JOIN address sa ON sa.id = s.address_id "
        "  WHERE ca.label = 'Home' "
        "    AND ST_DWithin(ha.geo, sa.geo, s.delivery_radius_km * 1000)"
        ")"
    )
    result = await session.exec(sql)  # type: ignore[call-overload]
    assert bool(result.scalar_one()) is True


@pytest.mark.asyncio
async def test_pune_address_is_not_serviceable_for_any_store(
    session: AsyncSession,
) -> None:
    await seed_demo_data(session)
    sql = text(
        "SELECT COUNT(*) FROM customeraddress ca "
        "JOIN address ca_addr ON ca_addr.id = ca.address_id "
        "JOIN store s ON TRUE "
        "JOIN address sa ON sa.id = s.address_id "
        "WHERE ca.label = 'Pune Trip' "
        "  AND ST_DWithin(ca_addr.geo, sa.geo, s.delivery_radius_km * 1000)"
    )
    result = await session.exec(sql)  # type: ignore[call-overload]
    assert int(result.scalar_one()) == 0


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
    # Anchor application rows keep their canonical status.
    assert statuses["approved.seller@khanabazaar.dev"] == VerificationStatus.Approved
    assert statuses["pending.seller@khanabazaar.dev"] == VerificationStatus.Pending
    assert statuses["rejected.seller@khanabazaar.dev"] == VerificationStatus.Rejected
    # Total profiles match the application roster.
    assert len(statuses) == len(APPLICATIONS)
