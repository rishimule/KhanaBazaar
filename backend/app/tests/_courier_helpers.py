# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Shared world + HTTP helpers for the courier test files.

One Bengaluru store with a 5 km local radius and a 500 km courier radius, one
"Sweets" service with courier switched on, and a customer with three saved
addresses: local (~0.6 km), courier (Mysuru, ~128 km) and far (New Delhi,
~1,740 km). Later tasks append endpoint helpers to this module.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

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

STORE_POINT = (12.9716, 77.5946)  # Bengaluru
LOCAL_POINT = (12.9750, 77.5990)  # ~0.6 km from the store
COURIER_POINT = (12.2958, 76.6394)  # Mysuru, ~128 km
FAR_POINT = (28.6139, 77.2090)  # New Delhi, ~1,740 km

CUSTOMER = User(id=8101, email="courier-cust@kb.test", role=UserRole.Customer, is_active=True)
OTHER_CUSTOMER = User(id=8102, email="courier-other@kb.test", role=UserRole.Customer, is_active=True)
SELLER = User(id=8103, email="courier-seller@kb.test", role=UserRole.Seller, is_active=True)
OTHER_SELLER = User(id=8104, email="courier-other-seller@kb.test", role=UserRole.Seller, is_active=True)
ADMIN = User(id=8105, email="courier-admin@kb.test", role=UserRole.Admin, is_active=True)


@dataclass(frozen=True)
class CourierWorld:
    customer_profile_id: int
    seller_profile_id: int
    other_seller_profile_id: int
    store_id: int
    service_id: int
    sps_id: int
    inventory_id: int
    # CustomerAddress ids — what checkout's `customer_address_id` takes.
    local_address_id: int
    courier_address_id: int
    far_address_id: int


async def _address(
    session: AsyncSession,
    point: tuple[float, float],
    *,
    pincode: str,
    city: str,
    state: str,
    country: str = "India",
) -> Address:
    addr = Address(
        **make_address(
            latitude=point[0], longitude=point[1], pincode=pincode,
            city=city, state=state, country=country,
        )
    )
    session.add(addr)
    await session.flush()
    return addr


async def seed_courier_world(
    session: AsyncSession,
    *,
    courier_radius_km: float | None = 500.0,
    courier_enabled: bool = True,
    seller_status: VerificationStatus = VerificationStatus.Approved,
    price: float = 100.0,
    stock: int = 10,
    quantity: int = 2,
) -> CourierWorld:
    """Seed the courier world and return plain ids (no live ORM rows)."""
    for user in (CUSTOMER, OTHER_CUSTOMER, SELLER, OTHER_SELLER, ADMIN):
        session.add(User(**user.model_dump()))
    await session.flush()

    customer = CustomerProfile(
        user_id=CUSTOMER.id, first_name="Asha", last_name="Rao", phone="+919900000001"
    )
    other_customer = CustomerProfile(user_id=OTHER_CUSTOMER.id, first_name="Other")
    session.add_all([customer, other_customer])
    await session.flush()
    assert customer.id is not None

    link_ids: dict[str, int] = {}
    for key, point, pincode, city, state in (
        ("local", LOCAL_POINT, "560001", "Bengaluru", "Karnataka"),
        ("courier", COURIER_POINT, "570001", "Mysuru", "Karnataka"),
        ("far", FAR_POINT, "110001", "New Delhi", "Delhi"),
    ):
        addr = await _address(session, point, pincode=pincode, city=city, state=state)
        link = CustomerAddress(
            customer_profile_id=customer.id, address_id=addr.id, is_default=key == "local"
        )
        session.add(link)
        await session.flush()
        assert link.id is not None
        link_ids[key] = link.id

    business = await _address(
        session, STORE_POINT, pincode="560002", city="Bengaluru", state="Karnataka"
    )
    seller = SellerProfile(
        user_id=SELLER.id, first_name="Ravi", phone="+919900000002",
        business_name="Ravi Sweets", verification_status=seller_status,
        business_address_id=business.id,
        upi_vpa="ravi@okaxis", upi_enabled=True,
        bank_account_name="Ravi Sweets", bank_account_number="123456789012",
        bank_ifsc="HDFC0001234", bank_transfer_enabled=True,
    )
    other_business = await _address(
        session, STORE_POINT, pincode="560003", city="Bengaluru", state="Karnataka"
    )
    other_seller = SellerProfile(
        user_id=OTHER_SELLER.id, first_name="Mira", phone="+919900000003",
        business_name="Mira Mart", verification_status=VerificationStatus.Approved,
        business_address_id=other_business.id, upi_vpa="mira@okaxis", upi_enabled=True,
    )
    session.add_all([seller, other_seller])
    await session.flush()
    assert seller.id is not None and other_seller.id is not None

    store_addr = await _address(
        session, STORE_POINT, pincode="560004", city="Bengaluru", state="Karnataka"
    )
    store = Store(
        name="Ravi Sweets", seller_profile_id=seller.id, address_id=store_addr.id,
        delivery_radius_km=5.0, courier_radius_km=courier_radius_km, pin_confirmed=True,
    )
    other_store_addr = await _address(
        session, STORE_POINT, pincode="560005", city="Bengaluru", state="Karnataka"
    )
    other_store = Store(
        name="Mira Mart", seller_profile_id=other_seller.id, address_id=other_store_addr.id
    )
    session.add_all([store, other_store])
    await session.flush()
    assert store.id is not None

    service = Service(slug="sweets", is_active=True, sort_order=0)
    session.add(service)
    await session.flush()
    assert service.id is not None
    session.add(ServiceTranslation(service_id=service.id, language_code="en", name="Sweets"))
    sps = SellerProfileService(
        seller_profile_id=seller.id, service_id=service.id,
        free_delivery_threshold=500.0, delivery_fee=30.0, courier_enabled=courier_enabled,
    )
    session.add(sps)
    session.add(SellerProfileService(seller_profile_id=other_seller.id, service_id=service.id))
    await session.flush()
    assert sps.id is not None

    category = Category(service_id=service.id, slug="mithai", is_active=True, sort_order=0)
    session.add(category)
    await session.flush()
    session.add(CategoryTranslation(category_id=category.id, language_code="en", name="Mithai"))
    sub = Subcategory(category_id=category.id, slug="barfi", is_active=True, sort_order=0)
    session.add(sub)
    await session.flush()
    session.add(SubcategoryTranslation(subcategory_id=sub.id, language_code="en", name="Barfi"))
    product = MasterProduct(subcategory_id=sub.id, slug="kaju-katli", base_price=price)
    session.add(product)
    await session.flush()
    session.add(
        MasterProductTranslation(
            master_product_id=product.id, language_code="en",
            name="Kaju Katli", description="500 g box",
        )
    )
    inventory = StoreInventory(
        store_id=store.id, product_id=product.id, price=price, stock=stock, is_available=True
    )
    session.add(inventory)
    await session.flush()
    assert inventory.id is not None

    cart = Cart(customer_profile_id=customer.id, store_id=store.id, service_id=service.id)
    session.add(cart)
    await session.flush()
    session.add(CartItem(cart_id=cart.id, inventory_id=inventory.id, quantity=quantity))
    await session.commit()

    return CourierWorld(
        customer_profile_id=customer.id,
        seller_profile_id=seller.id,
        other_seller_profile_id=other_seller.id,
        store_id=store.id,
        service_id=service.id,
        sps_id=sps.id,
        inventory_id=inventory.id,
        local_address_id=link_ids["local"],
        courier_address_id=link_ids["courier"],
        far_address_id=link_ids["far"],
    )


@asynccontextmanager
async def client_as(user: User) -> AsyncIterator[AsyncClient]:
    """An HTTP client authenticated as `user` (overrides get_current_user)."""
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_current_user, None)


from datetime import datetime, timezone  # noqa: E402

from app.models.commerce import (  # noqa: E402
    Delivery,
    DeliveryMode,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.courier import CourierQuote, OrderCourier  # noqa: E402


async def insert_courier_order(
    session: AsyncSession,
    world: CourierWorld,
    *,
    status: OrderStatus = OrderStatus.Pending,
    subtotal: float = 200.0,
    delivery_fee: float = 0.0,
    payment_status: PaymentStatus = PaymentStatus.Pending,
    payment_method: PaymentMethod = PaymentMethod.Upi,
    quote_fee: float | None = None,
    quote_days: tuple[int, int] = (3, 5),
    claimed: bool = False,
) -> int:
    """Insert a courier order straight into the DB, bypassing checkout — for
    the comms and reminder tests, which only need the rows."""
    link = await session.get(CustomerAddress, world.courier_address_id)
    assert link is not None
    order = Order(
        customer_profile_id=world.customer_profile_id, store_id=world.store_id,
        service_id=world.service_id, service_name_snapshot="Sweets",
        delivery_address_id=link.address_id, delivery_address_snapshot="Mysuru 570001",
        delivery_mode=DeliveryMode.Courier, status=status,
        subtotal=subtotal, delivery_fee=delivery_fee, tax=0.0, total=subtotal + delivery_fee,
    )
    session.add(order)
    await session.flush()
    assert order.id is not None
    session.add(Payment(
        order_id=order.id, amount=subtotal + delivery_fee, method=payment_method,
        status=payment_status,
        customer_claimed_at=datetime.now(timezone.utc) if claimed else None,
    ))
    session.add(Delivery(order_id=order.id))
    session.add(OrderCourier(
        order_id=order.id, recipient_name="Asha Rao", recipient_phone="+919900000001",
    ))
    if quote_fee is not None:
        session.add(CourierQuote(
            order_id=order.id, version=1, courier_fee=quote_fee,
            eta_min_days=quote_days[0], eta_max_days=quote_days[1],
            carrier_name="DTDC", created_by_user_id=SELLER.id,
        ))
    await session.commit()
    return order.id


from typing import Any  # noqa: E402


async def place_courier_order(
    world: CourierWorld,
    *,
    payment_method: str = "upi",
    address_id: int | None = None,
    recipient_name: str = "Asha Rao",
    recipient_phone: str = "+919900000001",
    apply_store_credit: bool = True,
) -> dict[str, Any]:
    """Place the seeded cart as a courier order to the Mysuru address."""
    async with client_as(CUSTOMER) as ac:
        resp = await ac.post("/api/v1/orders", json={
            "customer_address_id": address_id or world.courier_address_id,
            "store_id": world.store_id,
            "service_id": world.service_id,
            "payment_method": payment_method,
            "delivery_mode": "courier",
            "recipient_name": recipient_name,
            "recipient_phone": recipient_phone,
            "apply_store_credit": apply_store_credit,
        })
    assert resp.status_code == 201, resp.text
    return resp.json()


import httpx  # noqa: E402


async def send_quote(
    order_id: int,
    *,
    fee: float = 120.0,
    min_days: int = 3,
    max_days: int = 5,
    carrier: str | None = "DTDC",
    note: str | None = None,
    as_user: User = SELLER,
) -> httpx.Response:
    async with client_as(as_user) as ac:
        return await ac.post(f"/api/v1/orders/{order_id}/courier/quote", json={
            "courier_fee": fee, "eta_min_days": min_days, "eta_max_days": max_days,
            "carrier_name": carrier, "note": note,
        })


async def get_order(order_id: int, *, as_user: User = CUSTOMER) -> dict[str, Any]:
    async with client_as(as_user) as ac:
        resp = await ac.get(f"/api/v1/orders/{order_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()
