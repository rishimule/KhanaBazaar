# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select

from app.models.admin_audit import AdminActionLog
from app.models.base import User, UserRole


async def _persist_test_admin(session):
    """admin_auth_headers uses a fake admin id=99001; persist it so the
    admin_action_log.admin_user_id FK resolves on audited writes."""
    if await session.get(User, 99001) is None:
        session.add(
            User(id=99001, email="admin-test@kb.com", role=UserRole.Admin, is_active=True)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_admin_patch_and_get_credit_config(
    client, session, approved_seller, admin_auth_headers
):
    await _persist_test_admin(session)
    seller_id = approved_seller["profile"].id

    # Default (no row yet) reads as disabled + 0 cap.
    r = await client.get(
        f"/api/v1/admin/sellers/{seller_id}/credit-config", headers=admin_auth_headers
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"credit_enabled": False, "max_limit_per_customer": 0.0}

    # Enable + set cap.
    r = await client.patch(
        f"/api/v1/admin/sellers/{seller_id}/credit-config",
        json={"credit_enabled": True, "max_limit_per_customer": 5000},
        headers=admin_auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"credit_enabled": True, "max_limit_per_customer": 5000.0}

    # Persisted + audited.
    r = await client.get(
        f"/api/v1/admin/sellers/{seller_id}/credit-config", headers=admin_auth_headers
    )
    assert r.json()["credit_enabled"] is True
    audit = (
        await session.exec(
            select(AdminActionLog).where(AdminActionLog.action == "credit.set_config")
        )
    ).all()
    assert len(audit) == 1
    assert audit[0].target_seller_id == seller_id


@pytest.mark.asyncio
async def test_credit_config_requires_admin(client, approved_seller, customer_auth_headers):
    seller_id = approved_seller["profile"].id
    r = await client.get(
        f"/api/v1/admin/sellers/{seller_id}/credit-config", headers=customer_auth_headers
    )
    assert r.status_code == 403
