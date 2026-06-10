# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import pytest

from app.models.seller_profile_change_request import (
    SellerProfileChangeGroup,
    SellerProfileChangeStatus,
)
from app.services.seller_profile_change_requests import (
    approve,
    create_change_request,
)


@pytest.mark.asyncio
async def test_avatar_cr_approve_sets_live_fields(approved_seller, session, admin_user):
    profile = approved_seller["profile"]
    create = await create_change_request(
        session=session,
        seller_profile=profile,
        group=SellerProfileChangeGroup.Avatar,
        proposed={
            "avatar_url": "/media/avatars/seller/1/x.webp",
            "storage_key": "avatars/seller/1/x.webp",
        },
        note=None,
        actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    assert "avatar_url" in create.cr.baseline_json
    await approve(
        session=session, cr=create.cr, admin_user_id=admin_user.id, applied=None, note=None
    )
    await session.commit()
    await session.refresh(profile)
    assert profile.avatar_url == "/media/avatars/seller/1/x.webp"
    assert profile.avatar_storage_key == "avatars/seller/1/x.webp"
    assert create.cr.status is SellerProfileChangeStatus.Approved


@pytest.mark.asyncio
async def test_avatar_cr_removal_clears_fields(approved_seller, session, admin_user):
    profile = approved_seller["profile"]
    profile.avatar_url = "/media/avatars/seller/1/old.webp"
    profile.avatar_storage_key = "avatars/seller/1/old.webp"
    session.add(profile)
    await session.commit()
    create = await create_change_request(
        session=session,
        seller_profile=profile,
        group=SellerProfileChangeGroup.Avatar,
        proposed={"avatar_url": ""},
        note=None,
        actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    await approve(
        session=session, cr=create.cr, admin_user_id=admin_user.id, applied=None, note=None
    )
    await session.commit()
    await session.refresh(profile)
    assert profile.avatar_url is None
    assert profile.avatar_storage_key is None
