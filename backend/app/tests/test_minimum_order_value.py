# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
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

mock_customer = User(id=701, email="mov-cust@kb.com", role=UserRole.Customer, is_active=True)
mock_seller = User(id=702, email="mov-seller@kb.com", role=UserRole.Seller, is_active=True)
mock_admin = User(id=703, email="mov-admin@kb.com", role=UserRole.Admin, is_active=True)


@pytest.fixture(autouse=True)
async def patch_email_dispatch() -> AsyncGenerator[None, None]:
    with (
        patch("app.api.orders.dispatch_order_placed"),
        patch("app.api.orders.dispatch_order_status_changed"),
    ):
        yield


@pytest.fixture(autouse=True)
async def seed(session: AsyncSession) -> AsyncGenerator[dict[str, int], None]:
    for u in (mock_customer, mock_seller, mock_admin):
        session.add(User(**u.model_dump()))
    await session.flush()

    customer = CustomerProfile(user_id=mock_customer.id, first_name="C")
    session.add(customer)
    await session.flush()

    cust_addr = Address(**make_address(pincode="560300", latitude=12.9716, longitude=77.5946))
    session.add(cust_addr)
    await session.flush()
    session.add(CustomerAddress(
        customer_profile_id=customer.id, address_id=cust_addr.id, is_default=True,
    ))

    seller_addr = Address(**make_address(pincode="560301", latitude=12.9716, longitude=77.5946))
    session.add(seller_addr)
    await session.flush()
    seller = SellerProfile(
        user_id=mock_seller.id, first_name="S", phone="+919811000702",
        business_name="Shop", bank_account_number="2", bank_ifsc="HDFC0000002",
        verification_status=VerificationStatus.Approved,
        business_address_id=seller_addr.id,
    )
    session.add(seller)
    await session.flush()

    store_addr = Address(**make_address(pincode="560302", latitude=12.9716, longitude=77.5946))
    session.add(store_addr)
    await session.flush()
    store = Store(name="Shop", seller_profile_id=seller.id, address_id=store_addr.id)
    session.add(store)
    await session.flush()

    grocery = Service(slug="grocery")
    session.add(grocery)
    await session.flush()
    session.add(ServiceTranslation(service_id=grocery.id, language_code="en", name="Grocery"))
    sps = SellerProfileService(seller_profile_id=seller.id, service_id=grocery.id)
    session.add(sps)
    await session.flush()

    category = Category(service_id=grocery.id, slug="g-cat")
    session.add(category)
    await session.flush()
    session.add(CategoryTranslation(category_id=category.id, language_code="en", name="g-cat"))
    subcat = Subcategory(category_id=category.id, slug="g-sub")
    session.add(subcat)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=subcat.id, language_code="en", name="g-sub"))
    product = MasterProduct(subcategory_id=subcat.id, slug="rice", base_price=50.0)
    session.add(product)
    await session.flush()
    session.add(MasterProductTranslation(
        master_product_id=product.id, language_code="en", name="Rice", description="Rice",
    ))
    await session.flush()
    inv = StoreInventory(
        store_id=store.id, product_id=product.id, price=50.0, stock=10, is_available=True,
    )
    session.add(inv)
    await session.flush()

    cart = Cart(customer_profile_id=customer.id, store_id=store.id, service_id=grocery.id)
    session.add(cart)
    await session.flush()
    session.add(CartItem(cart_id=cart.id, inventory_id=inv.id, quantity=1))  # subtotal = 50

    cust_address_id = (await session.exec(
        select(CustomerAddress.id).where(CustomerAddress.customer_profile_id == customer.id)
    )).first()
    assert cust_address_id is not None
    ids = {
        "customer_address_id": cust_address_id,
        "store_id": store.id,
        "service_id": grocery.id,
        "seller_id": seller.id,
        "sps_id": sps.id,
    }
    await session.commit()
    yield ids  # type: ignore[misc]


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_current_user] = lambda: mock_customer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def seller_client_factory():  # noqa: ANN201
    @asynccontextmanager
    async def _make(user: User):  # noqa: ANN202
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    return _make


async def _set_delivery(
    session: AsyncSession, sps_id: int, threshold: float, fee: float = 10.0
) -> None:
    sps = await session.get(SellerProfileService, sps_id)
    assert sps is not None
    sps.free_delivery_threshold = threshold
    sps.delivery_fee = fee
    await session.commit()


async def test_checkout_below_minimum_rejected(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    await _set_delivery(session, seed["sps_id"], 100.0)  # subtotal 50 < 100
    resp = await client.post("/api/v1/orders", json={
        "customer_address_id": seed["customer_address_id"],
        "store_id": seed["store_id"],
        "service_id": seed["service_id"],
        "payment_method": "upi",
    })
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["detail"] == "below_minimum_order_value"
    assert detail["min_order_value"] == 100.0
    assert detail["subtotal"] == 50.0
    assert detail["shortfall"] == 50.0
    # Cart must survive the rejection.
    assert len((await session.exec(select(Cart))).all()) == 1


async def test_checkout_at_minimum_succeeds(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    await _set_delivery(session, seed["sps_id"], 50.0)  # subtotal 50 == 50
    resp = await client.post("/api/v1/orders", json={
        "customer_address_id": seed["customer_address_id"],
        "store_id": seed["store_id"],
        "service_id": seed["service_id"],
        "payment_method": "upi",
    })
    assert resp.status_code == 201, resp.text


async def test_checkout_zero_minimum_no_enforcement(
    client: AsyncClient, seed: dict[str, int],
) -> None:
    # Default min_order_value is 0.0 — order should place.
    resp = await client.post("/api/v1/orders", json={
        "customer_address_id": seed["customer_address_id"],
        "store_id": seed["store_id"],
        "service_id": seed["service_id"],
        "payment_method": "upi",
    })
    assert resp.status_code == 201, resp.text


async def test_seller_sets_min_order_value(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    # Approved sellers now route min-order edits through change-requests; the
    # direct self-PATCH endpoint stays available for Pending sellers iterating
    # on a not-yet-approved profile, so flip the seed to Pending here.
    seller_row = (await session.exec(
        select(SellerProfile).where(SellerProfile.id == seed["seller_id"])
    )).first()
    seller_row.verification_status = VerificationStatus.Pending
    await session.commit()
    async with seller_client_factory(mock_seller) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/me/services/{seed['service_id']}",
            json={"free_delivery_threshold": 150.0, "delivery_fee": 20.0},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["free_delivery_threshold"] == 150.0
    assert resp.json()["delivery_fee"] == 20.0
    sps = await session.get(SellerProfileService, seed["sps_id"])
    await session.refresh(sps)
    assert sps.free_delivery_threshold == 150.0
    assert sps.delivery_fee == 20.0


async def test_seller_set_min_rejects_negative(
    seller_client_factory, seed: dict[str, int],
) -> None:
    async with seller_client_factory(mock_seller) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/me/services/{seed['service_id']}",
            json={"free_delivery_threshold": -5, "delivery_fee": 0},
        )
    assert resp.status_code == 422


async def test_seller_set_min_unknown_service_404(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    # Same as test_seller_sets_min_order_value: flip the seller out of Approved
    # so the 404 path is reachable (Approved sellers hit the use_change_request
    # 409 guard before the service lookup).
    seller_row = (await session.exec(
        select(SellerProfile).where(SellerProfile.id == seed["seller_id"])
    )).first()
    seller_row.verification_status = VerificationStatus.Pending
    await session.commit()
    async with seller_client_factory(mock_seller) as ac:
        resp = await ac.patch(
            "/api/v1/sellers/me/services/999999",
            json={"free_delivery_threshold": 10.0, "delivery_fee": 0},
        )
    assert resp.status_code == 404


async def test_seller_set_min_rejects_above_cap(
    seller_client_factory, seed: dict[str, int],
) -> None:
    async with seller_client_factory(mock_seller) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/me/services/{seed['service_id']}",
            json={"free_delivery_threshold": 100001, "delivery_fee": 0},
        )
    assert resp.status_code == 422


async def test_admin_set_min_unknown_service_404(
    seller_client_factory, seed: dict[str, int],
) -> None:
    # Approved seller (default seed) but a service id they do not offer.
    async with seller_client_factory(mock_admin) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller.id}/services/999999",
            json={"free_delivery_threshold": 10.0, "delivery_fee": 0},
        )
    assert resp.status_code == 404


async def test_min_persists_across_profile_service_save(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    # Set a minimum, then re-save the profile with the same service set still
    # selected. replace_profile_services leaves the existing row untouched, so
    # the minimum must survive. (Service set is locked after approval, so this
    # path uses a Pending seller.)
    await _set_delivery(session, seed["sps_id"], 80.0)
    seller = (await session.exec(
        select(SellerProfile).where(SellerProfile.id == seed["seller_id"])
    )).first()
    seller.verification_status = VerificationStatus.Pending
    await session.commit()

    async with seller_client_factory(mock_seller) as ac:
        resp = await ac.patch("/api/v1/sellers/me/profile", json={
            "full_name": "S Seller",
            "business_name": "Shop",
            "phone": "+919811000702",
            "gst_number": None,
            "fssai_license": None,
            "bank_account_number": "2",
            "bank_ifsc": "HDFC0000002",
            "service_ids": [seed["service_id"]],
            "address": make_address(pincode="560301"),
        })
    assert resp.status_code in (200, 204), resp.text
    sps = await session.get(SellerProfileService, seed["sps_id"])
    await session.refresh(sps)
    assert sps.free_delivery_threshold == 80.0


async def test_admin_sets_min_order_value(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    async with seller_client_factory(mock_admin) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller.id}/services/{seed['service_id']}",
            json={"free_delivery_threshold": 200.0, "delivery_fee": 15.0},
        )
    assert resp.status_code == 200, resp.text
    sps = await session.get(SellerProfileService, seed["sps_id"])
    await session.refresh(sps)
    assert sps.free_delivery_threshold == 200.0
    assert sps.delivery_fee == 15.0
    # Audit row written.
    from app.models.admin_audit import AdminActionLog
    logs = (await session.exec(select(AdminActionLog))).all()
    assert any(row.action == "service.set_delivery_settings" for row in logs)


async def test_admin_set_min_rejects_non_approved_seller(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    seller = (await session.exec(
        select(SellerProfile).where(SellerProfile.id == seed["seller_id"])
    )).first()
    seller.verification_status = VerificationStatus.Pending
    await session.commit()
    async with seller_client_factory(mock_admin) as ac:
        resp = await ac.patch(
            f"/api/v1/sellers/admin/{mock_seller.id}/services/{seed['service_id']}",
            json={"free_delivery_threshold": 50.0, "delivery_fee": 0},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "seller_not_active"


async def test_cart_read_includes_min_order_value(
    client: AsyncClient, session: AsyncSession, seed: dict[str, int],
) -> None:
    await _set_delivery(session, seed["sps_id"], 120.0)
    resp = await client.get("/api/v1/carts")
    assert resp.status_code == 200, resp.text
    carts = resp.json()["carts"]
    assert len(carts) == 1
    assert carts[0]["free_delivery_threshold"] == 120.0


async def test_admin_hub_includes_services_with_min(
    seller_client_factory, session: AsyncSession, seed: dict[str, int],
) -> None:
    await _set_delivery(session, seed["sps_id"], 90.0)
    async with seller_client_factory(mock_admin) as ac:
        resp = await ac.get(f"/api/v1/admin/sellers/{mock_seller.id}")
    assert resp.status_code == 200, resp.text
    services = resp.json()["services"]
    assert len(services) == 1
    assert services[0]["id"] == seed["service_id"]
    assert services[0]["free_delivery_threshold"] == 90.0
