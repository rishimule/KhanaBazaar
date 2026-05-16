# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.address import Address
from app.models.admin_audit import AdminActionLog, AdminActionTargetType
from app.models.base import User, UserRole
from app.models.profile import SellerProfile, VerificationStatus
from app.services.admin_audit import log as audit_log
from tests._helpers import make_address


async def _seed_admin_and_seller(
    session: AsyncSession,
    admin_email: str,
    seller_email: str,
    phone: str,
) -> tuple[User, SellerProfile]:
    admin = User(email=admin_email, role=UserRole.Admin, is_active=True)
    seller_user = User(email=seller_email, role=UserRole.Seller, is_active=True)
    session.add(admin)
    session.add(seller_user)
    await session.flush()
    address = Address(**make_address())
    session.add(address)
    await session.flush()
    seller_profile = SellerProfile(
        user_id=seller_user.id,
        first_name="A",
        business_name="Audit Helper Test Store",
        phone=phone,
        verification_status=VerificationStatus.Approved,
        business_address_id=address.id,
    )
    session.add(seller_profile)
    await session.commit()
    await session.refresh(admin)
    await session.refresh(seller_profile)
    return admin, seller_profile


@pytest.mark.asyncio
async def test_audit_log_helper_adds_row_in_session_without_committing(
    session: AsyncSession,
) -> None:
    """The helper must add a row to the OPEN session but not commit."""
    admin, seller_profile = await _seed_admin_and_seller(
        session, "admin-aud@kb.com", "seller-aud@kb.com", "+919811000001"
    )
    admin_id, seller_profile_id = admin.id, seller_profile.id

    await audit_log(
        session=session,
        admin_user_id=admin_id,
        target_seller_id=seller_profile_id,
        target_type=AdminActionTargetType.Inventory,
        target_id=999,
        action="inventory.update",
        before_json={"price": 100},
        after_json={"price": 150},
        reason="price correction",
    )

    # Helper must not commit on its own. After our explicit commit() the row
    # should be persisted.
    await session.commit()
    rows = list((await session.exec(select(AdminActionLog))).all())
    assert len(rows) == 1
    row = rows[0]
    assert row.admin_user_id == admin_id
    assert row.target_seller_id == seller_profile_id
    assert row.target_id == 999
    assert row.action == "inventory.update"
    assert row.before_json == {"price": 100}
    assert row.after_json == {"price": 150}
    assert row.reason == "price correction"


@pytest.mark.asyncio
async def test_audit_log_helper_rolls_back_with_session(
    session: AsyncSession,
) -> None:
    """If the surrounding transaction rolls back, the audit row must NOT persist."""
    admin, seller_profile = await _seed_admin_and_seller(
        session, "admin-rb@kb.com", "seller-rb@kb.com", "+919811000002"
    )
    admin_id, seller_profile_id = admin.id, seller_profile.id

    await audit_log(
        session=session,
        admin_user_id=admin_id,
        target_seller_id=seller_profile_id,
        target_type=AdminActionTargetType.Order,
        target_id=42,
        action="order.cancel",
    )
    await session.rollback()

    rows = list((await session.exec(select(AdminActionLog))).all())
    assert rows == []
