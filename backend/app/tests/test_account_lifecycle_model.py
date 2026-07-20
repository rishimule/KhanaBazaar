# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import AccountStatus, User, UserRole
from app.models.customer_account_event import CustomerAccountEvent


@pytest.mark.asyncio
async def test_new_user_defaults_to_active(session: AsyncSession) -> None:
    user = User(email="lifecycle-default@kb.com", role=UserRole.Customer)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    assert user.account_status == AccountStatus.active
    assert user.is_active is True
    assert user.status_changed_at is None


@pytest.mark.asyncio
async def test_customer_account_event_table_name_and_write(session: AsyncSession) -> None:
    # Explicit __tablename__ must be the snake_case name (SQLModel would
    # otherwise default to "customeraccountevent").
    assert CustomerAccountEvent.__tablename__ == "customer_account_event"
    user = User(email="lifecycle-event@kb.com", role=UserRole.Customer)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    assert user.id is not None
    ev = CustomerAccountEvent(
        user_id=user.id,
        actor_user_id=None,
        actor_role="customer",
        from_status=AccountStatus.active,
        to_status=AccountStatus.deactivated,
        reason="testing",
    )
    session.add(ev)
    await session.commit()
    rows = (
        await session.exec(
            select(CustomerAccountEvent).where(CustomerAccountEvent.user_id == user.id)
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].to_status == AccountStatus.deactivated
    assert rows[0].actor_role == "customer"
