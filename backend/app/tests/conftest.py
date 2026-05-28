# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
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

# Point search infra at the test Meilisearch instance before any test imports
# app.search.client. The client is process-wide, so we override the env first.
os.environ["MEILI_URL"] = os.environ.get("MEILI_TEST_URL", "http://localhost:7701")
os.environ["MEILI_MASTER_KEY"] = os.environ.get("MEILI_TEST_KEY", "test-master-key")

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
    # Build a fresh fakeredis bound to this test's event loop. The previous
    # instance (if any) was tied to a closed loop and would raise
    # "Event loop is closed" on the next .incr/.set call.
    _fake_redis_holder["r"] = FakeRedis(decode_responses=True)
    # Same problem applies to the real-redis client lru-cached in
    # app.core.redis._make_redis — tests that bypass the dep override (e.g.
    # geo `_geo_rate_limit` which calls get_redis() directly) reuse the
    # client bound to the first test's loop. Drop the cache so each test
    # gets a fresh client bound to its own loop.
    from app.core import redis as _redis_mod
    _redis_mod._make_redis.cache_clear()
    # Flush real-redis state too so rate-limit counters and cached values
    # don't leak across tests / CI re-runs.
    try:
        _real_redis = _redis_mod._make_redis()
        await _real_redis.flushdb()
    except Exception:
        pass
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

# Override Redis with a per-test fakeredis instance so rate-limit counters
# and serviceable caches don't leak across tests (and don't depend on a real
# Redis running on the host). A fresh FakeRedis is rebuilt by the autouse
# `setup_test_db` fixture for each test function, then exposed to the
# `get_redis` dependency override via this holder dict. Recreating per-test
# avoids "Event loop is closed" errors that come from binding FakeRedis to
# a now-dead loop when pytest-asyncio uses a per-function loop scope.
from fakeredis.aioredis import FakeRedis  # noqa: E402

from app.core.redis import get_redis  # noqa: E402

_fake_redis_holder: dict[str, FakeRedis | None] = {"r": None}


async def _override_redis() -> FakeRedis:
    r = _fake_redis_holder["r"]
    if r is None:
        # Should only happen outside an autouse fixture window.
        r = FakeRedis(decode_responses=True)
        _fake_redis_holder["r"] = r
    return r


app.dependency_overrides[get_redis] = _override_redis


# Force `async_session_factory()` (used by Celery tasks + CLI tools) to bind to
# the test engine so any code path that creates its own session inside a test
# sees the same data the test seeded.
from app.db import session as _db_session_mod  # noqa: E402

_db_session_mod.engine = test_engine
_db_session_mod.async_session_factory = lambda: AsyncSession(test_engine, expire_on_commit=False)

@pytest.fixture(name="session")
async def session_fixture() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        yield session

@pytest.fixture(name="client")
async def client_fixture() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ─── Admin/customer dependency-override fixtures + seeded catalog rows ──
# Used by the catalog-admin test suite. Plain pytest fixtures so each test
# can pick which auth role it wants (admin / customer / anonymous) without
# shipping JWTs.


@pytest.fixture(name="admin_auth_headers")
def admin_auth_headers_fixture() -> Generator[dict[str, str], None, None]:
    from app.core.security import get_current_admin, get_current_user
    from app.models.base import User, UserRole

    admin = User(id=99001, email="admin-test@kb.com", role=UserRole.Admin, is_active=True)
    app.dependency_overrides[get_current_admin] = lambda: admin
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        yield {"X-Test-Role": "admin"}
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(name="customer_auth_headers")
def customer_auth_headers_fixture() -> Generator[dict[str, str], None, None]:
    from app.core.security import get_current_user
    from app.models.base import User, UserRole

    customer = User(id=99002, email="cust-test@kb.com", role=UserRole.Customer, is_active=True)
    app.dependency_overrides[get_current_user] = lambda: customer
    try:
        yield {"X-Test-Role": "customer"}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


class _Stub:
    """Plain holder for ids returned from seed fixtures.

    Returning live SQLModel rows past `commit()` would expire attributes;
    a stub avoids touching the session again from test code.
    """

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture(name="seeded_service")
async def seeded_service_fixture(session: AsyncSession) -> _Stub:
    from app.models.catalog import Service, ServiceTranslation

    svc = Service(slug="seeded-svc", is_active=True, sort_order=0)
    session.add(svc)
    await session.flush()
    assert svc.id is not None
    svc_id = svc.id
    session.add(ServiceTranslation(service_id=svc_id, language_code="en", name="Seeded Service"))
    await session.commit()
    return _Stub(id=svc_id, slug="seeded-svc")


@pytest.fixture(name="seeded_category")
async def seeded_category_fixture(
    session: AsyncSession, seeded_service: _Stub
) -> _Stub:
    from app.models.catalog import Category, CategoryTranslation

    cat = Category(
        service_id=seeded_service.id, slug="seeded-cat", is_active=True, sort_order=0
    )
    session.add(cat)
    await session.flush()
    assert cat.id is not None
    cat_id = cat.id
    session.add(CategoryTranslation(category_id=cat_id, language_code="en", name="Seeded Category"))
    await session.commit()
    return _Stub(id=cat_id, slug="seeded-cat", service_id=seeded_service.id)


@pytest.fixture(name="seeded_subcategory")
async def seeded_subcategory_fixture(
    session: AsyncSession, seeded_category: _Stub
) -> _Stub:
    from app.models.catalog import Subcategory, SubcategoryTranslation

    sub = Subcategory(
        category_id=seeded_category.id, slug="seeded-sub", is_active=True, sort_order=0
    )
    session.add(sub)
    await session.flush()
    assert sub.id is not None
    sub_id = sub.id
    session.add(
        SubcategoryTranslation(subcategory_id=sub_id, language_code="en", name="Seeded Subcategory")
    )
    await session.commit()
    return _Stub(id=sub_id, slug="seeded-sub", category_id=seeded_category.id)


@pytest.fixture(autouse=True)
def _stub_search_celery_delays() -> Generator[None, None, None]:
    """Replace Celery `.delay()` on every search task with a no-op so listener
    fan-out during seed flushes never tries to run async DB work on a different
    event loop (eager-mode collision). Tests that need to assert .delay() was
    called supply their own `patch()` inside the test body — the inner patch
    overrides this autouse stub for the duration of the with-block.
    """
    from unittest.mock import patch

    targets = [
        "app.search.tasks.reindex_master_product.delay",
        "app.search.tasks.reindex_store.delay",
        "app.search.tasks.reindex_products_for_store.delay",
        "app.search.tasks.reindex_products_by_subcategory.delay",
        "app.search.tasks.reindex_products_by_category.delay",
        "app.search.tasks.rebuild_search_terms.delay",
        "app.search.tasks.prune_query_log.delay",
    ]
    patches = [patch(t, lambda *a, **kw: None) for t in targets]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()


@pytest.fixture(name="meili_test_client")
async def meili_test_client_fixture() -> AsyncGenerator[Any, None]:
    """Per-test Meilisearch client. Wipes known indexes and re-applies settings."""
    from meilisearch_python_sdk import AsyncClient

    from app.search import client as client_mod
    from app.search.bootstrap import ensure_indexes
    # Force re-creation so each test gets a fresh client pointed at the test URL.
    if client_mod._client is not None:
        await client_mod._client.aclose()
        client_mod._client = None

    ac = AsyncClient(os.environ["MEILI_URL"], os.environ["MEILI_MASTER_KEY"])
    for uid in ("products", "stores", "search_terms"):
        try:
            task = await ac.index(uid).delete()
            await ac.wait_for_task(task.task_uid)
        except Exception:
            pass
    await ensure_indexes(ac)
    # Make get_meili_client() return this same client during the test
    client_mod._client = ac
    try:
        yield ac
    finally:
        await ac.aclose()
        client_mod._client = None


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
    if "test_customer_welcome_email" in request.node.nodeid:
        # This test exercises the real dispatcher → Celery task wiring.
        yield
        return
    from unittest.mock import patch

    with patch("app.api.orders.dispatch_order_placed", lambda *a, **kw: None), \
         patch("app.api.orders.dispatch_order_status_changed", lambda *a, **kw: None), \
         patch("app.api.orders.dispatch_notification_push", lambda *a, **kw: None), \
         patch("app.api.orders.dispatch_admin_order_action", lambda *a, **kw: None), \
         patch("app.api.admin_actions.dispatch_admin_order_action", lambda *a, **kw: None), \
         patch("app.api.sellers.dispatch_seller_approved", lambda *a, **kw: None), \
         patch("app.api.sellers.dispatch_seller_rejected", lambda *a, **kw: None), \
         patch("app.api.sellers.dispatch_seller_application_submitted", lambda *a, **kw: None), \
         patch("app.services.seller_emails.dispatch_seller_application_submitted", lambda *a, **kw: None), \
         patch("app.services.seller_emails.dispatch_customer_welcome", lambda *a, **kw: None), \
         patch("app.services.seller_emails.dispatch_seller_change_request_submitted", lambda *a, **kw: None), \
         patch("app.services.seller_emails.dispatch_seller_change_request_approved", lambda *a, **kw: None), \
         patch("app.services.seller_emails.dispatch_seller_change_request_changes_requested", lambda *a, **kw: None), \
         patch("app.services.seller_emails.dispatch_seller_change_request_rejected", lambda *a, **kw: None), \
         patch("app.services.seller_profile_change_requests.dispatch_seller_change_request_submitted", lambda *a, **kw: None, create=True), \
         patch("app.services.seller_profile_change_requests.dispatch_seller_change_request_approved", lambda *a, **kw: None, create=True), \
         patch("app.services.seller_profile_change_requests.dispatch_seller_change_request_changes_requested", lambda *a, **kw: None, create=True), \
         patch("app.services.seller_profile_change_requests.dispatch_seller_change_request_rejected", lambda *a, **kw: None, create=True):
        yield


# ─── Seller-profile-change-request fixtures ──────────────────────────────
import uuid as _uuid  # noqa: E402

import pytest_asyncio  # noqa: E402

from app.models.address import Address  # noqa: E402
from app.models.base import User, UserRole  # noqa: E402
from app.models.profile import SellerProfile, VerificationStatus  # noqa: E402
from tests._helpers import make_address as _make_address_dict  # noqa: E402


async def _make_address(session: AsyncSession) -> Address:
    addr = Address(**_make_address_dict())
    session.add(addr)
    await session.flush()
    return addr


async def _make_seller(
    session: AsyncSession, *, status: VerificationStatus
) -> dict[str, Any]:
    user = User(
        email=f"s-{_uuid.uuid4().hex[:8]}@x.test", role=UserRole.Seller
    )
    session.add(user)
    await session.flush()
    addr = await _make_address(session)
    profile = SellerProfile(
        user_id=user.id,
        first_name="Anita",
        last_name="K",
        phone=f"+9198{_uuid.uuid4().int % 100000000:08d}",
        business_name="Anita Stores",
        verification_status=status,
        business_address_id=addr.id,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(user)
    await session.refresh(profile)
    return {"user": user, "profile": profile, "address": addr}


@pytest_asyncio.fixture
async def approved_seller(session: AsyncSession) -> dict[str, Any]:
    return await _make_seller(session, status=VerificationStatus.Approved)


@pytest_asyncio.fixture
async def pending_seller(session: AsyncSession) -> dict[str, Any]:
    return await _make_seller(session, status=VerificationStatus.Pending)


@pytest_asyncio.fixture
async def admin_user(session: AsyncSession) -> User:
    user = User(
        email=f"a-{_uuid.uuid4().hex[:8]}@x.test", role=UserRole.Admin
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
