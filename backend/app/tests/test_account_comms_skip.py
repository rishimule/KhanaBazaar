# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import AccountStatus, User, UserRole
from app.models.commerce import DeliveryMode, Order, OrderStatus
from app.models.notification import Notification
from app.models.profile import CustomerProfile


def _in_memory_order(customer_profile_id: int) -> Order:
    """Unpersisted Order; the comms guard short-circuits on account_status
    before it touches any FK-backed field."""
    order = Order(
        customer_profile_id=customer_profile_id,
        store_id=1,
        service_id=1,
        service_name_snapshot="Grocery",
        delivery_address_id=1,
        delivery_mode=DeliveryMode.DoorDelivery,
        status=OrderStatus.Pending,
        subtotal=0.0,
        delivery_fee=0.0,
        tax=0.0,
        total=0.0,
        delivery_address_snapshot="x",
    )
    order.id = 424242
    return order


@pytest.mark.asyncio
async def test_no_notification_row_for_deleted_customer(session: AsyncSession) -> None:
    user = User(
        email="comms-del@kb.com", role=UserRole.Customer,
        account_status=AccountStatus.deleted, is_active=False,
    )
    session.add(user)
    await session.flush()
    assert user.id is not None
    profile = CustomerProfile(user_id=user.id, first_name="Gone")
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    assert profile.id is not None

    from app.api.orders import record_and_dispatch_notification

    await record_and_dispatch_notification(
        session, _in_memory_order(profile.id), "pending"
    )
    rows = (
        await session.exec(
            select(Notification).where(Notification.customer_profile_id == profile.id)
        )
    ).all()
    assert rows == []
