# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_customer
from app.models.base import User, UserRole
from app.models.profile import CustomerProfile

pytestmark = pytest.mark.asyncio


async def test_support_queues_email(client: AsyncClient, session: AsyncSession):
    user = User(email="s@example.com", role=UserRole.Customer, is_active=True)
    session.add(user)
    await session.flush()
    user_id = user.id
    assert user_id is not None
    session.add(CustomerProfile(user_id=user_id, first_name="S"))
    await session.commit()

    view = User(
        id=user_id, email="s@example.com", role=UserRole.Customer, is_active=True
    )
    app.dependency_overrides[get_current_customer] = lambda: view
    with patch("app.worker.send_support_email") as task:
        try:
            r = await client.post(
                "/api/v1/customers/me/support",
                json={"subject": "hi", "message": "hello"},
            )
        finally:
            app.dependency_overrides.pop(get_current_customer, None)
    assert r.status_code == 202
    task.delay.assert_called_once_with("s@example.com", "hi", "hello")
