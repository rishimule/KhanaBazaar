# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_seller
from app.models.notification import NotificationType
from app.services.notifications import record_seller_notification


@pytest.mark.asyncio
async def test_seller_lists_and_reads_notifications(
    client: AsyncClient, session: AsyncSession, approved_seller_with_store
) -> None:
    spid = approved_seller_with_store.profile.id
    await record_seller_notification(
        session, seller_profile_id=spid, type=NotificationType.FeeExpiring,
        title="Expiring", body="Your plan expires soon.", status_value="expiring",
    )
    await session.commit()
    app.dependency_overrides[get_current_seller] = lambda: approved_seller_with_store.user
    try:
        r = await client.get("/api/v1/sellers/me/notifications")
        assert r.status_code == 200
        assert r.json()["unread_count"] == 1
        nid = r.json()["notifications"][0]["id"]
        r2 = await client.post(f"/api/v1/sellers/me/notifications/{nid}/read")
        assert r2.status_code == 204
        r3 = await client.get("/api/v1/sellers/me/notifications")
        assert r3.json()["unread_count"] == 0
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
