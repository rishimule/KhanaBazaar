from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.base import User

@pytest.mark.asyncio
async def test_create_user(session: AsyncSession) -> None:
    # 1. Create a user
    new_user = User(
        firebase_uid="test_uid_123",
        email="test_db_user@example.com",
        full_name="Test DB User",
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    assert new_user.id is not None
    assert new_user.firebase_uid == "test_uid_123"

    # 2. Read the user back
    statement = select(User).where(User.firebase_uid == "test_uid_123")
    result = await session.exec(statement)
    db_user = result.first()

    assert db_user is not None
    assert db_user.id == new_user.id

    # 3. Clean up the user
    await session.delete(db_user)
    await session.commit()
