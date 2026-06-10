# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import io
from pathlib import Path
from typing import Any, AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.config import settings
from app.core.security import get_current_seller, get_current_user
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.profile import SellerProfile, VerificationStatus
from tests._helpers import make_address

mock_seller = User(id=7501, email="avatar-seller@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def seed_approved_seller(session: AsyncSession) -> AsyncGenerator[None, None]:
    session.add(User(**mock_seller.model_dump()))
    await session.flush()
    addr = Address(**make_address())
    session.add(addr)
    await session.flush()
    profile = SellerProfile(
        user_id=mock_seller.id,
        first_name="Ava",
        business_name="Ava Store",
        phone="+919811117501",
        verification_status=VerificationStatus.Approved,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.commit()
    yield


@pytest.fixture
def override_as_seller() -> Iterator[None]:
    app.dependency_overrides[get_current_seller] = lambda: mock_seller
    app.dependency_overrides[get_current_user] = lambda: mock_seller
    yield None
    app.dependency_overrides.pop(get_current_seller, None)
    app.dependency_overrides.pop(get_current_user, None)


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), "orange").save(buf, format="PNG")
    return buf.getvalue()


async def test_seller_avatar_upload_creates_cr(
    override_as_seller: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "MEDIA_LOCAL_DIR", str(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/sellers/me/avatar",
            files={"file": ("a.png", _png(), "image/png")},
        )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["group"] == "avatar"
    assert body["status"] == "submitted"
    assert body["proposed_json"]["avatar_url"]
