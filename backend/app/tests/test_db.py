from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User


async def test_create_user(session: AsyncSession) -> None:
    new_user = User(email="test_db_user@example.com", full_name="Test DB User")
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    assert new_user.id is not None
    assert new_user.email == "test_db_user@example.com"

    statement = select(User).where(User.email == "test_db_user@example.com")
    result = await session.exec(statement)
    db_user = result.first()

    assert db_user is not None
    assert db_user.id == new_user.id

    await session.delete(db_user)
    await session.commit()
