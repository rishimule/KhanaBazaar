# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any


async def test_auth_session_row_roundtrip(session: Any) -> None:
    from app.models.auth_session import AuthSession
    from app.models.base import User, UserRole

    user = User(email="sess@x.test", role=UserRole.Customer)
    session.add(user)
    await session.flush()
    now = datetime.now(timezone.utc)
    row = AuthSession(
        user_id=user.id,
        refresh_token_hash="deadbeef",
        trusted=True,
        last_used_at=now,
        absolute_expires_at=now + timedelta(days=180),
        device_label="Chrome on Windows",
        user_agent="Mozilla/5.0",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    assert row.id is not None
    assert row.revoked_at is None
    assert row.prev_token_hash is None
    assert row.trusted is True
    assert row.device_label == "Chrome on Windows"
