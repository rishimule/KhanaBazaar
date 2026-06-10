# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import io

import pytest
from PIL import Image
from sqlmodel import select

from app.core.config import settings
from app.models.seller_profile_change_request import (
    SellerProfileChangeGroup,
    SellerProfileChangeRequest,
    SellerProfileChangeStatus,
)
from app.services.seller_profile_change_requests import create_avatar_change_request


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), "purple").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_avatar_upload_creates_cr(approved_seller, session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))
    profile = approved_seller["profile"]
    res = await create_avatar_change_request(
        session=session, seller_profile=profile, raw=_png(),
        actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    assert res.cr.group is SellerProfileChangeGroup.Avatar
    assert res.cr.status is SellerProfileChangeStatus.Submitted
    assert res.cr.proposed_json["avatar_url"]


@pytest.mark.asyncio
async def test_second_upload_supersedes_first(approved_seller, session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))
    profile = approved_seller["profile"]
    first = await create_avatar_change_request(
        session=session, seller_profile=profile, raw=_png(),
        actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    second = await create_avatar_change_request(
        session=session, seller_profile=profile, raw=_png(),
        actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    await session.refresh(first.cr)
    assert first.cr.status is SellerProfileChangeStatus.Withdrawn
    assert second.cr.status is SellerProfileChangeStatus.Submitted
    open_crs = (
        await session.exec(
            select(SellerProfileChangeRequest).where(
                SellerProfileChangeRequest.group == SellerProfileChangeGroup.Avatar,
                SellerProfileChangeRequest.status == SellerProfileChangeStatus.Submitted,
            )
        )
    ).all()
    assert len(open_crs) == 1


@pytest.mark.asyncio
async def test_reject_deletes_pending_blob(approved_seller, session, admin_user, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))
    from app.services.seller_profile_change_requests import reject

    profile = approved_seller["profile"]
    res = await create_avatar_change_request(
        session=session, seller_profile=profile, raw=_png(),
        actor_user_id=approved_seller["user"].id,
    )
    await session.commit()
    key = res.cr.proposed_json["storage_key"]
    assert (tmp_path / key).exists()
    await reject(
        session=session, cr=res.cr, admin_user_id=admin_user.id,
        reason="not appropriate",
    )
    await session.commit()
    assert not (tmp_path / key).exists()
