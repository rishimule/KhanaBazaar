# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from fakeredis.aioredis import FakeRedis

from app.core import dev_otp_log
from app.core.config import settings


@pytest.fixture
def redis():
    return FakeRedis(decode_responses=True)


async def test_record_is_noop_when_disabled(redis, monkeypatch):
    monkeypatch.setattr(settings, "EXPOSE_DEV_OTPS", False)
    await dev_otp_log.record_otp(redis, "a@b.com", "123456", namespace="email")
    assert await dev_otp_log.recent_otps(redis) == []


async def test_record_then_read_when_enabled(redis, monkeypatch):
    monkeypatch.setattr(settings, "EXPOSE_DEV_OTPS", True)
    await dev_otp_log.record_otp(redis, "a@b.com", "123456", namespace="email")
    await dev_otp_log.record_otp(redis, "+919811110100", "654321", namespace="phone")
    rows = await dev_otp_log.recent_otps(redis)
    # Newest first.
    assert rows[0]["to"] == "+919811110100"
    assert rows[0]["code"] == "654321"
    assert rows[0]["purpose"] == "phone"
    assert "ts" in rows[0]
    assert rows[1]["to"] == "a@b.com"


async def test_list_is_capped(redis, monkeypatch):
    monkeypatch.setattr(settings, "EXPOSE_DEV_OTPS", True)
    for i in range(150):
        await dev_otp_log.record_otp(redis, f"u{i}@b.com", f"{i:06d}", namespace="email")
    rows = await dev_otp_log.recent_otps(redis, limit=500)
    assert len(rows) == 100  # LTRIM keeps newest 100
