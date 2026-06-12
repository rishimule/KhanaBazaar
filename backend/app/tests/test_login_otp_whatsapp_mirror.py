# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import whatsapp as whatsapp_mod
from app.models.base import User, UserRole
from app.models.profile import CustomerProfile


@pytest.mark.asyncio
async def test_login_otp_mirrors_to_whatsapp_for_verified_customer(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whatsapp_mod.settings, "WHATSAPP_PROVIDER", "console")
    whatsapp_mod.get_whatsapp_sender.cache_clear()
    user = User(email="cust@example.com", role=UserRole.Customer)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    session.add(
        CustomerProfile(
            user_id=user.id, first_name="A", last_name="B",
            phone="+919999999999",
            phone_verified_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    with patch("app.worker.send_login_otp_whatsapp_async.delay") as mock_delay:
        resp = await client.post(
            "/api/v1/auth/otp/request", json={"email": "cust@example.com"}
        )
    assert resp.status_code == 200
    mock_delay.assert_called_once()
    args = mock_delay.call_args.args
    assert args[1] == "+919999999999"  # (code, phone)
    whatsapp_mod.get_whatsapp_sender.cache_clear()


@pytest.mark.asyncio
async def test_login_otp_no_mirror_when_whatsapp_disabled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whatsapp_mod.settings, "WHATSAPP_PROVIDER", "none")
    whatsapp_mod.get_whatsapp_sender.cache_clear()
    with patch("app.worker.send_login_otp_whatsapp_async.delay") as mock_delay:
        resp = await client.post(
            "/api/v1/auth/otp/request", json={"email": "nobody@example.com"}
        )
    assert resp.status_code == 200
    mock_delay.assert_not_called()
    whatsapp_mod.get_whatsapp_sender.cache_clear()


@pytest.mark.asyncio
async def test_login_otp_no_mirror_when_phone_unverified(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whatsapp_mod.settings, "WHATSAPP_PROVIDER", "console")
    whatsapp_mod.get_whatsapp_sender.cache_clear()
    user = User(email="unverified@example.com", role=UserRole.Customer)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    session.add(
        CustomerProfile(
            user_id=user.id, first_name="C", phone="+918888888888",
            phone_verified_at=None,
        )
    )
    await session.commit()

    with patch("app.worker.send_login_otp_whatsapp_async.delay") as mock_delay:
        resp = await client.post(
            "/api/v1/auth/otp/request", json={"email": "unverified@example.com"}
        )
    assert resp.status_code == 200
    mock_delay.assert_not_called()
    whatsapp_mod.get_whatsapp_sender.cache_clear()
