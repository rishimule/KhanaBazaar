from typing import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_user
from app.models.base import User, UserRole
from app.models.catalog import Service, ServiceTranslation

mock_admin = User(id=1, email="admin@kb.com", role=UserRole.Admin, is_active=True)


async def _add_service(
    session: AsyncSession, slug: str, name: str, sort_order: int = 0,
    is_active: bool = True,
) -> Service:
    service = Service(slug=slug, is_active=is_active, sort_order=sort_order)
    session.add(service)
    await session.flush()
    session.add(
        ServiceTranslation(
            service_id=service.id,
            language_code="en",
            name=name,
            description=None,
        )
    )
    await session.flush()
    return service


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    session.add(User(**mock_admin.model_dump()))
    await session.flush()

    grocery = await _add_service(session, "grocery", "Grocery", sort_order=0)
    electronics = await _add_service(session, "electronics", "Electronics", sort_order=1)
    pharmacy = await _add_service(session, "pharmacy", "Pharmacy", sort_order=2)
    inactive = await _add_service(session, "hidden", "Hidden", sort_order=99, is_active=False)
    assert grocery.id is not None
    assert electronics.id is not None
    assert pharmacy.id is not None
    assert inactive.id is not None
    ids = {
        "grocery": grocery.id,
        "electronics": electronics.id,
        "pharmacy": pharmacy.id,
        "inactive": inactive.id,
    }
    await session.commit()
    yield ids


@pytest.fixture
def override_as_admin() -> Iterator[None]:
    app.dependency_overrides[get_current_admin] = lambda: mock_admin
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    yield
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_list_services_excludes_inactive_and_orders_by_sort_order() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/catalog/services")
    assert resp.status_code == 200
    body = resp.json()
    slugs = [s["slug"] for s in body]
    assert slugs == ["grocery", "electronics", "pharmacy"]
    assert body[0]["name"] == "Grocery"
    assert body[1]["name"] == "Electronics"
    assert all(s["is_active"] is True for s in body)


@pytest.mark.asyncio
async def test_create_category_with_explicit_service_id(
    seed: dict[str, int], override_as_admin: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/catalog/categories",
            json={"name": "Phones & Tablets", "service_id": seed["electronics"]},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Phones & Tablets"
    assert body["service_id"] == seed["electronics"]


@pytest.mark.asyncio
async def test_create_category_without_service_falls_back_to_grocery(
    seed: dict[str, int], override_as_admin: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/catalog/categories",
            json={"name": "Snacks"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["service_id"] == seed["grocery"]


@pytest.mark.asyncio
async def test_create_category_invalid_service_id_returns_400(
    override_as_admin: None,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/catalog/categories",
            json={"name": "Bogus", "service_id": 9999},
        )
    assert resp.status_code == 400
    assert "Service" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_categories_returns_service_id(
    seed: dict[str, int], override_as_admin: None
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create = await ac.post(
            "/api/v1/catalog/categories",
            json={"name": "OTC Medicines", "service_id": seed["pharmacy"]},
        )
        assert create.status_code == 200, create.text
        listing = await ac.get("/api/v1/catalog/categories")
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["service_id"] == seed["pharmacy"]
