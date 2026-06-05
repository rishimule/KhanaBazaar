# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.asyncio
async def test_dev_email_table_roundtrips(session: AsyncSession) -> None:
    from app.models.dev_email import DevEmail

    session.add(
        DevEmail(
            to_email="a@b.com",
            subject="Hi",
            body_text="body",
            body_html="<p>body</p>",
            reply_to="support@x.com",
            category=None,
            provider="console",
        )
    )
    await session.commit()
    rows = (await session.exec(select(DevEmail))).all()
    assert len(rows) == 1
    assert rows[0].to_email == "a@b.com"
    assert rows[0].id is not None


@pytest.mark.asyncio
async def test_dev_sms_table_roundtrips(session: AsyncSession) -> None:
    from app.models.dev_sms import DevSms

    session.add(DevSms(to_phone="+919812345678", body="code 1234", provider="console"))
    await session.commit()
    rows = (await session.exec(select(DevSms))).all()
    assert len(rows) == 1
    assert rows[0].to_phone == "+919812345678"
