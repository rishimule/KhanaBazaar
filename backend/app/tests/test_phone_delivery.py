# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any

import pytest

from app.core.phone_delivery import deliver_phone_message


class _RecordingSMS:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def send(self, to: str, text: str) -> None:
        self.calls.append((to, text))


class _OKWhatsApp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    async def send_template(
        self, to: str, template: Any, variables: dict[str, str]
    ) -> None:
        self.calls.append((to, template.name, variables))


class _FailingWhatsApp:
    async def send_template(
        self, to: str, template: Any, variables: dict[str, str]
    ) -> None:
        raise RuntimeError("not on whatsapp")


@pytest.mark.asyncio
async def test_prefers_whatsapp_when_sender_present() -> None:
    sms, wa = _RecordingSMS(), _OKWhatsApp()
    channel = await deliver_phone_message(
        to="+918888888888",
        template_name="otp_seller_phone",
        variables={"code": "111111"},
        sms_text="sms copy",
        sms_sender=sms,
        whatsapp_sender=wa,
    )
    assert channel == "whatsapp"
    assert wa.calls == [("+918888888888", "otp_seller_phone", {"code": "111111"})]
    assert sms.calls == []


@pytest.mark.asyncio
async def test_falls_back_to_sms_when_whatsapp_raises() -> None:
    sms = _RecordingSMS()
    channel = await deliver_phone_message(
        to="+918888888888",
        template_name="otp_seller_phone",
        variables={"code": "111111"},
        sms_text="sms copy",
        sms_sender=sms,
        whatsapp_sender=_FailingWhatsApp(),
    )
    assert channel == "sms"
    assert sms.calls == [("+918888888888", "sms copy")]


@pytest.mark.asyncio
async def test_uses_sms_when_whatsapp_disabled() -> None:
    sms = _RecordingSMS()
    channel = await deliver_phone_message(
        to="+918888888888",
        template_name="otp_seller_phone",
        variables={"code": "111111"},
        sms_text="sms copy",
        sms_sender=sms,
        whatsapp_sender=None,
    )
    assert channel == "sms"
    assert sms.calls == [("+918888888888", "sms copy")]
