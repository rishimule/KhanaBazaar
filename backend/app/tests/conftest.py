import asyncio
from typing import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.db.session import get_db_session

# Use a test Postgres database
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar_test"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True, scope="function")
async def setup_test_db() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    from app.models.catalog import Language

    async with AsyncSession(test_engine) as session:
        for code, name, native in (
            ("en", "English", "English"),
            ("hi", "Hindi", "हिन्दी"),
            ("mr", "Marathi", "मराठी"),
            ("gu", "Gujarati", "ગુજરાતી"),
            ("pa", "Punjabi", "ਪੰਜਾਬੀ"),
        ):
            session.add(Language(code=code, name=name, native_name=native, is_active=True))
        await session.commit()
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(test_engine) as session:
        yield session

app.dependency_overrides[get_db_session] = override_get_db_session

@pytest.fixture(name="session")
async def session_fixture() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(test_engine) as session:
        yield session

@pytest.fixture(name="client")
async def client_fixture() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
