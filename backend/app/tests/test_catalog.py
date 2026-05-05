from typing import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_admin, get_current_user
from app.models.base import User, UserRole
from app.models.catalog import (
    Category,
    CategoryTranslation,
    MasterProduct,
    MasterProductTranslation,
    Service,
    ServiceTranslation,
    Subcategory,
    SubcategoryTranslation,
)

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


_GROCERY_TRANSLATIONS = {
    "en": "Grocery",
    "hi": "किराना",
    "mr": "किराणा",
    "gu": "કરિયાણું",
    "pa": "ਕਰਿਆਨਾ",
}


async def _seed_grocery_translations(session: AsyncSession, service_id: int) -> None:
    for code, name in _GROCERY_TRANSLATIONS.items():
        if code == "en":
            continue  # already seeded by autouse seed fixture
        session.add(
            ServiceTranslation(
                service_id=service_id, language_code=code, name=name, description=None
            )
        )
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,expected_name", list(_GROCERY_TRANSLATIONS.items()))
async def test_list_services_returns_localized_name(
    session: AsyncSession, seed: dict[str, int], lang: str, expected_name: str
) -> None:
    await _seed_grocery_translations(session, seed["grocery"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/catalog/services", headers={"Accept-Language": lang}
        )
    assert resp.status_code == 200
    body = resp.json()
    grocery = next(s for s in body if s["slug"] == "grocery")
    assert grocery["name"] == expected_name


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


_FRUITS_VEG_TRANSLATIONS = {
    "en": "Fruits & Vegetables",
    "hi": "फल और सब्ज़ियां",
    "mr": "फळे आणि भाज्या",
    "gu": "ફળો અને શાકભાજી",
    "pa": "ਫਲ ਅਤੇ ਸਬਜ਼ੀਆਂ",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,expected_name", list(_FRUITS_VEG_TRANSLATIONS.items()))
async def test_list_categories_returns_localized_name(
    session: AsyncSession, seed: dict[str, int], lang: str, expected_name: str
) -> None:
    category = Category(service_id=seed["grocery"], slug="fruits-vegetables", sort_order=0)
    session.add(category)
    await session.flush()
    assert category.id is not None
    for code, name in _FRUITS_VEG_TRANSLATIONS.items():
        session.add(
            CategoryTranslation(
                category_id=category.id, language_code=code, name=name, description=None
            )
        )
    await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/catalog/categories", headers={"Accept-Language": lang}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert any(c["name"] == expected_name for c in body), body


async def _seed_category_with_subcategories(
    session: AsyncSession,
    service_id: int,
    category_name: str,
    subcategory_names: list[str],
) -> tuple[int, dict[str, int]]:
    category = Category(service_id=service_id, slug=category_name.lower().replace(" ", "-"))
    session.add(category)
    await session.flush()
    assert category.id is not None
    session.add(
        CategoryTranslation(
            category_id=category.id, language_code="en", name=category_name, description=None
        )
    )
    sub_ids: dict[str, int] = {}
    for sort_order, sub_name in enumerate(subcategory_names):
        sub = Subcategory(
            category_id=category.id,
            slug=sub_name.lower().replace(" ", "-"),
            sort_order=sort_order,
        )
        session.add(sub)
        await session.flush()
        assert sub.id is not None
        session.add(
            SubcategoryTranslation(
                subcategory_id=sub.id, language_code="en", name=sub_name, description=None
            )
        )
        sub_ids[sub_name] = sub.id
    await session.flush()
    return category.id, sub_ids


_LEAFY_GREENS_TRANSLATIONS = {
    "en": "Leafy Greens",
    "hi": "हरी पत्तेदार सब्ज़ियां",
    "mr": "हिरव्या पालेभाज्या",
    "gu": "પાંદડાવાળી શાકભાજી",
    "pa": "ਪੱਤੇਦਾਰ ਸਾਗ",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,expected_name", list(_LEAFY_GREENS_TRANSLATIONS.items()))
async def test_list_subcategories_returns_localized_name(
    session: AsyncSession, seed: dict[str, int], lang: str, expected_name: str
) -> None:
    category = Category(service_id=seed["grocery"], slug="fruits-vegetables", sort_order=0)
    session.add(category)
    await session.flush()
    assert category.id is not None
    sub = Subcategory(category_id=category.id, slug="leafy-greens", sort_order=0)
    session.add(sub)
    await session.flush()
    assert sub.id is not None
    for code, name in _LEAFY_GREENS_TRANSLATIONS.items():
        session.add(
            SubcategoryTranslation(
                subcategory_id=sub.id, language_code=code, name=name, description=None
            )
        )
    await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/catalog/subcategories", headers={"Accept-Language": lang}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert any(s["name"] == expected_name for s in body), body


@pytest.mark.asyncio
async def test_list_subcategories_returns_translated_names(
    session: AsyncSession, seed: dict[str, int]
) -> None:
    await _seed_category_with_subcategories(
        session,
        seed["grocery"],
        "Fruits & Vegetables",
        ["Leafy Greens", "Roots", "Fruits"],
    )
    await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/catalog/subcategories")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    names = [r["name"] for r in rows]
    assert names == ["Leafy Greens", "Roots", "Fruits"]
    assert all(r["category_id"] == rows[0]["category_id"] for r in rows)


@pytest.mark.asyncio
async def test_list_products_includes_subcategory_fields(
    session: AsyncSession, seed: dict[str, int]
) -> None:
    category_id, sub_ids = await _seed_category_with_subcategories(
        session,
        seed["grocery"],
        "Fruits & Vegetables",
        ["Leafy Greens"],
    )
    product = MasterProduct(
        subcategory_id=sub_ids["Leafy Greens"],
        slug="palak",
        image_url=None,
        base_price=28.0,
    )
    session.add(product)
    await session.flush()
    assert product.id is not None
    session.add(
        MasterProductTranslation(
            master_product_id=product.id,
            language_code="en",
            name="Spinach Bunch",
            description="Fresh palak",
        )
    )
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/catalog/products")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Spinach Bunch"
    assert row["category_id"] == category_id
    assert row["subcategory_id"] == sub_ids["Leafy Greens"]
    assert row["subcategory_name"] == "Leafy Greens"
