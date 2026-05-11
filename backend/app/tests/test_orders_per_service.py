# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
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
from app.models.commerce import Cart, CartItem
from app.models.profile import (
    CustomerAddress,
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory
from tests._helpers import make_address

mock_customer = User(id=501, email="ops-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=502, email="ops-seller@kb.com", role=UserRole.Seller, is_active=True)


@pytest.fixture(autouse=True)
async def patch_email_dispatch() -> AsyncGenerator[None, None]:
    with (
        patch("app.api.orders.dispatch_order_placed"),
        patch("app.api.orders.dispatch_order_status_changed"),
    ):
        yield


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    for u in (mock_customer, mock_seller):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer = CustomerProfile(user_id=mock_customer.id, first_name="C")
    session.add(customer)
    await session.flush()

    cust_addr = Address(
        **make_address(pincode="560300", latitude=12.9716, longitude=77.5946)
    )
    session.add(cust_addr)
    await session.flush()
    session.add(CustomerAddress(
        customer_profile_id=customer.id, address_id=cust_addr.id, is_default=True,
    ))

    seller_addr = Address(
        **make_address(pincode="560301", latitude=12.9716, longitude=77.5946)
    )
    session.add(seller_addr)
    await session.flush()
    seller = SellerProfile(
        user_id=mock_seller.id, first_name="S", phone="+919811000002",
        business_name="Shop", bank_account_number="2", bank_ifsc="HDFC0000002",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_addr.id,
    )
    session.add(seller)
    await session.flush()

    store_addr = Address(
        **make_address(pincode="560302", latitude=12.9716, longitude=77.5946)
    )
    session.add(store_addr)
    await session.flush()
    store = Store(name="Multi", seller_profile_id=seller.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()

    grocery = Service(slug="grocery")
    pharmacy = Service(slug="pharmacy")
    session.add_all([grocery, pharmacy])
    await session.flush()
    session.add_all([
        ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"),
        ServiceTranslation(service_id=pharmacy.id, language_code="en", name="Pharmacy"),
    ])
    session.add_all([
        SellerProfileService(seller_profile_id=seller.id, service_id=grocery.id),
        SellerProfileService(seller_profile_id=seller.id, service_id=pharmacy.id),
    ])
    await session.flush()

    async def _add_inventory(
        svc: Service, slug: str, name: str, price: float
    ) -> StoreInventory:
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

    g_inv = await _add_inventory(grocery, "ricesvc", "Rice", 50.0)
    p_inv = await _add_inventory(pharmacy, "paracsvc", "Paracetamol", 20.0)

    # Pre-populate both sub-baskets for the customer.
    g_cart = Cart(
        customer_profile_id=customer.id, store_id=store.id, service_id=grocery.id,
    )
    p_cart = Cart(
        customer_profile_id=customer.id, store_id=store.id, service_id=pharmacy.id,
    )
    session.add_all([g_cart, p_cart])
    await session.flush()
    session.add_all([
        CartItem(cart_id=g_cart.id, inventory_id=g_inv.id, quantity=1),
        CartItem(cart_id=p_cart.id, inventory_id=p_inv.id, quantity=1),
    ])

    # Capture all ids as plain ints BEFORE commit to avoid MissingGreenlet on yield.
    # Reads the customer address id while the rows are still loaded.
    cust_address_id = (
        await session.exec(select(CustomerAddress.id).where(
            CustomerAddress.customer_profile_id == customer.id
        ))
    ).first()
    assert cust_address_id is not None
    store_id = store.id
    grocery_id = grocery.id
    pharmacy_id = pharmacy.id
    grocery_inv_id = g_inv.id
    pharmacy_inv_id = p_inv.id
    seller_id = seller.id

    await session.commit()

    yield {
        "customer_address_id": cust_address_id,
        "store_id": store_id,
        "grocery_id": grocery_id,
        "pharmacy_id": pharmacy_id,
        "grocery_inv_id": grocery_inv_id,
        "pharmacy_inv_id": pharmacy_inv_id,
        "seller_id": seller_id,
    }


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


async def test_place_grocery_order_leaves_pharmacy_basket(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    resp = await client.post(
        "/api/v1/orders",
        json={
            "customer_address_id": seed["customer_address_id"],
            "store_id": seed["store_id"],
            "service_id": seed["grocery_id"],
            "payment_method": "upi",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["service_id"] == seed["grocery_id"]
    assert body["service_name"] == "Grocery"

    remaining = (await session.exec(select(Cart))).all()
    assert [c.service_id for c in remaining] == [seed["pharmacy_id"]]


async def test_seller_revoked_service_rejects_with_409(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    spsv = (await session.exec(
        select(SellerProfileService).where(
            SellerProfileService.seller_profile_id == seed["seller_id"],
            SellerProfileService.service_id == seed["pharmacy_id"],
        )
    )).first()
    assert spsv is not None
    await session.delete(spsv)
    await session.commit()

    resp = await client.post(
        "/api/v1/orders",
        json={
            "customer_address_id": seed["customer_address_id"],
            "store_id": seed["store_id"],
            "service_id": seed["pharmacy_id"],
            "payment_method": "upi",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "service_unavailable"

    remaining = (await session.exec(select(Cart))).all()
    assert len(remaining) == 2


async def test_catalog_drift_after_add_to_cart_raises_409(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    subcat = (await session.exec(
        select(Subcategory).join(
            MasterProduct, MasterProduct.subcategory_id == Subcategory.id,
        ).join(
            StoreInventory, StoreInventory.product_id == MasterProduct.id,
        ).where(StoreInventory.id == seed["grocery_inv_id"])
    )).first()
    assert subcat is not None
    category = (await session.exec(
        select(Category).where(Category.id == subcat.category_id)
    )).first()
    assert category is not None
    category.service_id = seed["pharmacy_id"]
    await session.commit()

    resp = await client.post(
        "/api/v1/orders",
        json={
            "customer_address_id": seed["customer_address_id"],
            "store_id": seed["store_id"],
            "service_id": seed["grocery_id"],
            "payment_method": "upi",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["detail"] == "service_mismatch"


async def test_list_orders_filter_by_service_id(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    for svc_id in (seed["grocery_id"], seed["pharmacy_id"]):
        resp = await client.post(
            "/api/v1/orders",
            json={
                "customer_address_id": seed["customer_address_id"],
                "store_id": seed["store_id"],
                "service_id": svc_id,
                "payment_method": "upi",
            },
        )
        assert resp.status_code == 201, resp.text

    grocery_only = (await client.get(
        f"/api/v1/orders?service_id={seed['grocery_id']}"
    )).json()["orders"]
    assert [o["service_id"] for o in grocery_only] == [seed["grocery_id"]]

    pharmacy_only = (await client.get(
        f"/api/v1/orders?service_id={seed['pharmacy_id']}"
    )).json()["orders"]
    assert [o["service_id"] for o in pharmacy_only] == [seed["pharmacy_id"]]


async def test_service_name_snapshot_uses_slug_when_translation_missing(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    row = (await session.exec(
        select(ServiceTranslation).where(
            ServiceTranslation.service_id == seed["grocery_id"],
            ServiceTranslation.language_code == "en",
        )
    )).first()
    assert row is not None
    await session.delete(row)
    await session.commit()

    resp = await client.post(
        "/api/v1/orders",
        json={
            "customer_address_id": seed["customer_address_id"],
            "store_id": seed["store_id"],
            "service_id": seed["grocery_id"],
            "payment_method": "upi",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["service_name"] == "grocery"
