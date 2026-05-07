import asyncio
import os
from typing import Any, AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# Run Celery tasks inline during tests so .delay() does not require a real
# Redis broker and email-task assertions can inspect side effects synchronously.
# The env var must be set before celery_app is imported below.
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")

from app import app  # noqa: E402
from app.core.celery_app import celery_app  # noqa: E402
from app.db.session import get_db_session  # noqa: E402

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

# Use a test Postgres database
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/khanabazaar_test"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

async def _reset_schema(conn: Any) -> None:
    """Drop and recreate the public schema to clear tables AND Postgres enum
    types. SQLModel.metadata.drop_all does not drop enum types, so reused
    types collide with `pg_type_typname_nsp_index` on the next create_all.
    Re-enables PostGIS after reset since its objects live in `public`."""
    from sqlalchemy import text

    await conn.execute(text("DROP SCHEMA public CASCADE"))
    await conn.execute(text("CREATE SCHEMA public"))
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))


async def _add_postgis_geo_column(conn: Any) -> None:
    """Add the address.geo generated column + GiST index after create_all.

    SQLModel metadata doesn't declare `geo` (it's raw DDL in the prod migration),
    so create_all skips it. Replicate the migration's DDL here so the test DB
    has schema parity with prod.
    """
    from sqlalchemy import text

    await conn.execute(text(
        "ALTER TABLE address ADD COLUMN geo geography(Point, 4326) "
        "GENERATED ALWAYS AS ("
        "  CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL "
        "       THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography "
        "       ELSE NULL END"
        ") STORED"
    ))
    await conn.execute(text("CREATE INDEX ix_address_geo ON address USING GIST (geo)"))


@pytest.fixture(autouse=True, scope="function")
async def setup_test_db() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await _reset_schema(conn)
        await conn.run_sync(SQLModel.metadata.create_all)
        await _add_postgis_geo_column(conn)
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
        await _reset_schema(conn)

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


@pytest.fixture(autouse=True)
def _patch_email_dispatch(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Mock order-email dispatchers as no-ops in every test except
    test_order_emails (which exercises the real tasks). The real dispatchers
    spawn a worker thread + open an engine to settings.DATABASE_URL (the dev
    database). In EAGER test mode this races with pytest-anyio's loop and
    the connection pool against the test DB, causing intermittent test
    pollution and snapshot isolation oddities."""
    if "test_order_emails" in request.node.nodeid:
        yield
        return
    from unittest.mock import patch

    with patch("app.api.orders.dispatch_order_placed", lambda *a, **kw: None), \
         patch("app.api.orders.dispatch_order_status_changed", lambda *a, **kw: None), \
         patch("app.api.sellers.dispatch_seller_approved", lambda *a, **kw: None), \
         patch("app.api.sellers.dispatch_seller_rejected", lambda *a, **kw: None):
        yield
