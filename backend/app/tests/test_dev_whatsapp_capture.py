# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import app.models as models
from app.models.dev_whatsapp import DevWhatsApp


def test_dev_whatsapp_is_registered():
    assert "DevWhatsApp" in models.__all__
    assert DevWhatsApp.__tablename__ == "dev_whatsapp"


def test_dev_whatsapp_fields():
    row = DevWhatsApp(to_phone="+918888888888", body="hi")
    assert row.provider == "console"
    assert row.template is None
    assert row.category is None


@pytest.mark.asyncio
async def test_record_outbound_whatsapp_persists(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import dev_mailbox
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    await dev_mailbox.record_outbound_whatsapp(
        to="+918888888888", body="Your code is 1", template="otp_login",
        category="AUTHENTICATION",
    )
    rows = (await session.exec(select(DevWhatsApp))).all()
    assert len(rows) == 1
    assert rows[0].to_phone == "+918888888888"
    assert rows[0].template == "otp_login"
    assert rows[0].category == "AUTHENTICATION"


@pytest.mark.asyncio
async def test_record_outbound_whatsapp_noop_outside_dev(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import dev_mailbox
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    await dev_mailbox.record_outbound_whatsapp(to="+918888888888", body="x")
    rows = (await session.exec(select(DevWhatsApp))).all()
    assert rows == []
