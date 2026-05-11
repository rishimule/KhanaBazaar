# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.core.security import get_current_user
from app.models.address import Address
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
from app.models.profile import (
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=401, email="psv-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=402, email="psv-seller@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    for u in (mock_customer, mock_seller):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer = CustomerProfile(user_id=mock_customer.id, first_name="C")
    session.add(customer)
    await session.flush()

    seller_addr = Address(**make_address(pincode="560200"))
    session.add(seller_addr)
    await session.flush()
    seller = SellerProfile(
        user_id=mock_seller.id, first_name="S", phone="+919811000001",
        business_name="X", bank_account_number="1", bank_ifsc="HDFC0000001",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_addr.id,
    )
    session.add(seller)
    await session.flush()

    store_addr = Address(**make_address(pincode="560201"))
    session.add(store_addr)
    await session.flush()
    store = Store(name="Store", seller_profile_id=seller.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()

    grocery = Service(slug="grocery")
    pharmacy = Service(slug="pharmacy")
    other_service = Service(slug="bakery")  # NOT offered by seller
    session.add_all([grocery, pharmacy, other_service])
    await session.flush()
    session.add_all([
        ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"),
        ServiceTranslation(service_id=pharmacy.id, language_code="en", name="Pharmacy"),
        ServiceTranslation(service_id=other_service.id, language_code="en", name="Bakery"),
    ])
    await session.flush()

    session.add_all([
        SellerProfileService(seller_profile_id=seller.id, service_id=grocery.id),
        SellerProfileService(seller_profile_id=seller.id, service_id=pharmacy.id),
    ])
    await session.flush()

    async def _add_inventory(svc: Service, slug: str, name: str, price: float) -> StoreInventory:
        category = Category(service_id=svc.id, slug=f"{slug}-cat")
        session.add(category)
        await session.flush()
        session.add(CategoryTranslation(
            category_id=category.id, language_code="en", name=f"{name}-cat",
        ))
        subcat = Subcategory(category_id=category.id, slug=f"{slug}-sub")
        session.add(subcat)
        await session.flush()
        session.add(SubcategoryTranslation(
            subcategory_id=subcat.id, language_code="en", name=f"{name}-sub",
        ))
        product = MasterProduct(subcategory_id=subcat.id, slug=slug, base_price=price)
        session.add(product)
        await session.flush()
        session.add(MasterProductTranslation(
            master_product_id=product.id, language_code="en", name=name, description=name,
        ))
        await session.flush()
        inv = StoreInventory(
            store_id=store.id, product_id=product.id, price=price, stock=10, is_available=True,
        )
        session.add(inv)
        await session.flush()
        return inv

    g_inv = await _add_inventory(grocery, "rice", "Rice", 50.0)
    p_inv = await _add_inventory(pharmacy, "paracetamol", "Paracetamol", 20.0)
    bakery_inv = await _add_inventory(other_service, "bread", "Bread", 30.0)
    # Note: bakery_inv is wired through the catalog but is NOT in the seller's
    # offered services — used to assert service_unavailable.

    # Capture ids as plain ints BEFORE commit. After commit() SQLAlchemy expires
    # instance attributes; accessing them during yield can trigger
    # MissingGreenlet (matches the pattern in tests/test_carts.py).
    assert store.id is not None
    assert grocery.id is not None
    assert pharmacy.id is not None
    assert other_service.id is not None
    assert g_inv.id is not None
    assert p_inv.id is not None
    assert bakery_inv.id is not None
    store_id = store.id
    grocery_id = grocery.id
    pharmacy_id = pharmacy.id
    bakery_id = other_service.id
    g_inv_id = g_inv.id
    p_inv_id = p_inv.id
    bakery_inv_id = bakery_inv.id

    await session.commit()

    yield {
        "store_id": store_id,
        "grocery_id": grocery_id,
        "pharmacy_id": pharmacy_id,
        "bakery_id": bakery_id,
        "grocery_inv_id": g_inv_id,
        "pharmacy_inv_id": p_inv_id,
        "bakery_inv_id": bakery_inv_id,
    }


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


async def test_cross_service_add_creates_two_sub_baskets(
    client: AsyncClient, seed: dict[str, int]
) -> None:
    for inv_id, svc_id in (
        (seed["grocery_inv_id"], seed["grocery_id"]),
        (seed["pharmacy_inv_id"], seed["pharmacy_id"]),
    ):
        resp = await client.post(
            "/api/v1/carts/items",
            json={
                "store_id": seed["store_id"],
                "service_id": svc_id,
                "inventory_id": inv_id,
                "quantity": 1,
            },
        )
        assert resp.status_code in (200, 201), resp.text

    listing = await client.get("/api/v1/carts/")
    assert listing.status_code == 200
    carts = listing.json()["carts"]
    assert len(carts) == 2
    store_ids = {c["store_id"] for c in carts}
    svc_ids = {c["service_id"] for c in carts}
    assert store_ids == {seed["store_id"]}
    assert svc_ids == {seed["grocery_id"], seed["pharmacy_id"]}


async def test_service_not_offered_by_seller_is_409(
    client: AsyncClient, seed: dict[str, int]
) -> None:
    resp = await client.post(
        "/api/v1/carts/items",
        json={
            "store_id": seed["store_id"],
            "service_id": seed["bakery_id"],
            "inventory_id": seed["bakery_inv_id"],
            "quantity": 1,
        },
    )
    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["detail"] == "service_unavailable"
    assert body["service_id"] == seed["bakery_id"]


async def test_inventory_service_mismatch_is_400(
    client: AsyncClient, seed: dict[str, int]
) -> None:
    # Inventory belongs to grocery but payload claims pharmacy.
    resp = await client.post(
        "/api/v1/carts/items",
        json={
            "store_id": seed["store_id"],
            "service_id": seed["pharmacy_id"],
            "inventory_id": seed["grocery_inv_id"],
            "quantity": 1,
        },
    )
    assert resp.status_code == 400
    body = resp.json()["detail"]
    assert body["detail"] == "service_mismatch"


async def test_globally_inactive_service_is_409(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int]
) -> None:
    from sqlmodel import select
    grocery = (await session.exec(
        select(Service).where(Service.id == seed["grocery_id"])
    )).first()
    assert grocery is not None
    grocery.is_active = False
    await session.commit()

    resp = await client.post(
        "/api/v1/carts/items",
        json={
            "store_id": seed["store_id"],
            "service_id": seed["grocery_id"],
            "inventory_id": seed["grocery_inv_id"],
            "quantity": 1,
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "service_unavailable"


async def test_delete_sub_basket_leaves_sibling(
    client: AsyncClient, seed: dict[str, int]
) -> None:
    for inv_id, svc_id in (
        (seed["grocery_inv_id"], seed["grocery_id"]),
        (seed["pharmacy_inv_id"], seed["pharmacy_id"]),
    ):
        await client.post(
            "/api/v1/carts/items",
            json={
                "store_id": seed["store_id"],
                "service_id": svc_id,
                "inventory_id": inv_id,
                "quantity": 1,
            },
        )

    dele = await client.delete(
        f"/api/v1/carts/{seed['store_id']}/{seed['grocery_id']}"
    )
    assert dele.status_code == 204

    listing = (await client.get("/api/v1/carts/")).json()["carts"]
    assert len(listing) == 1
    assert listing[0]["service_id"] == seed["pharmacy_id"]


async def test_sync_filters_service_mismatch_into_dropped(
    client: AsyncClient, seed: dict[str, int]
) -> None:
    resp = await client.post(
        "/api/v1/carts/sync",
        json={
            "carts": [
                {
                    "store_id": seed["store_id"],
                    "service_id": seed["pharmacy_id"],
                    "items": [
                        {"inventory_id": seed["pharmacy_inv_id"], "quantity": 1},
                        {"inventory_id": seed["grocery_inv_id"], "quantity": 1},
                    ],
                },
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    dropped = body["dropped"]
    assert any(
        d["inventory_id"] == seed["grocery_inv_id"]
        and d["reason"] == "service_mismatch"
        for d in dropped
    )
    assert len(body["carts"]) == 1
    assert body["carts"][0]["service_id"] == seed["pharmacy_id"]
    assert {i["inventory_id"] for i in body["carts"][0]["items"]} == {
        seed["pharmacy_inv_id"]
    }
