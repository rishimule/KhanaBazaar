# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import pytest

from app.core.otp_delivery import deliver_phone_otp


class _RecordingSMS:
    def __init__(self):
        self.calls = []

    async def send(self, to, text):
        self.calls.append((to, text))


class _OKWhatsApp:
    def __init__(self):
        self.calls = []

    async def send_template(self, to, template, variables):
        self.calls.append((to, template.name, variables))


class _FailingWhatsApp:
    async def send_template(self, to, template, variables):
        raise RuntimeError("not on whatsapp")


@pytest.mark.asyncio
async def test_prefers_whatsapp_when_available():
    sms, wa = _RecordingSMS(), _OKWhatsApp()
    channel = await deliver_phone_otp(
        to="+918888888888", template_name="otp_seller_phone",
        variables={"code": "111111"}, sms_text="sms copy",
        sms_sender=sms, whatsapp_sender=wa,
    )
    assert channel == "whatsapp"
    assert wa.calls == [("+918888888888", "otp_seller_phone", {"code": "111111"})]
    assert sms.calls == []


@pytest.mark.asyncio
async def test_falls_back_to_sms_on_whatsapp_failure():
    sms = _RecordingSMS()
    channel = await deliver_phone_otp(
        to="+918888888888", template_name="otp_seller_phone",
        variables={"code": "111111"}, sms_text="sms copy",
        sms_sender=sms, whatsapp_sender=_FailingWhatsApp(),
    )
    assert channel == "sms"
    assert sms.calls == [("+918888888888", "sms copy")]


@pytest.mark.asyncio
async def test_uses_sms_when_whatsapp_disabled():
    sms = _RecordingSMS()
    channel = await deliver_phone_otp(
        to="+918888888888", template_name="otp_seller_phone",
        variables={"code": "111111"}, sms_text="sms copy",
        sms_sender=sms, whatsapp_sender=None,
    )
    assert channel == "sms"
    assert sms.calls == [("+918888888888", "sms copy")]
