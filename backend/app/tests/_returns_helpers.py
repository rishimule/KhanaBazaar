# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Seeding helpers for the returns test suites.

Builds a delivered order owned by an approved seller who offers one service
with a configurable return window. Every returns test needs this, so it lives
here rather than being re-implemented per file.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from app import app
from app.models.address import Address
from app.models.base import User, UserRole
from app.models.catalog import Category, MasterProduct, Service, Subcategory
from app.models.commerce import (
    Delivery,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.consent import PolicyDocument, PolicyKind
from app.models.profile import (
    CustomerProfile,
    SellerProfile,
    SellerProfileService,
    VerificationStatus,
)
from app.models.store import Store, StoreInventory


@dataclass
class SeededOrder:
    customer_user: User
    customer_profile_id: int
    seller_user: User
    seller_profile_id: int
    store_id: int
    service_id: int
    order_id: int
    order_item_ids: list[int] = field(default_factory=list)
    inventory_ids: list[int] = field(default_factory=list)
    subtotal: float = 0.0
    delivery_fee: float = 0.0


_COUNTER = {"n": 0}


def _tag() -> str:
    """Short unique token. A counter keeps phone numbers deterministic-length
    and collision-free within a test run; uuid keeps them unique across runs."""
    _COUNTER["n"] += 1
    return f"{_COUNTER['n']:04d}{uuid.uuid4().hex[:4]}"


async def _address(session: AsyncSession, line1: str) -> int:
    addr = Address(
        address_line1=line1, city="Pune", state="Maharashtra",
        pincode="411001", country="India", latitude=18.5204, longitude=73.8567,
    )
    session.add(addr)
    await session.flush()
    assert addr.id is not None
    return addr.id


async def publish_return_agreement(session: AsyncSession, *, version: int = 1) -> int:
    """Publish a return agreement so initiation is not blocked."""
    session.add(
        PolicyDocument(
            kind=PolicyKind.return_agreement,
            version=version,
            body="Returned goods must be unused and in original packaging.",
        )
    )
    await session.commit()
    return version


async def seed_delivered_order(
    session: AsyncSession,
    *,
    delivered_days_ago: int = 1,
    return_window_days: int = 7,
    line_specs: Optional[list[tuple[str, float, int]]] = None,
    delivery_fee: float = 20.0,
    payment_method: PaymentMethod = PaymentMethod.Upi,
    order_status: OrderStatus = OrderStatus.Delivered,
    with_inventory: bool = False,
    email_suffix: str = "",
) -> SeededOrder:
    """Seed one delivered order. `line_specs` is (product_name, unit_price, qty)."""
    specs = line_specs or [("Ghee 1L", 250.0, 1), ("Atta 5kg", 300.0, 2)]
    tag = _tag()
    label = email_suffix or tag

    customer = User(email=f"cust-{label}-{tag}@x.test", role=UserRole.Customer, is_active=True)
    session.add(customer)
    await session.flush()
    assert customer.id is not None
    cprofile = CustomerProfile(
        user_id=customer.id, first_name="Riya",
        phone=f"+9188{int(tag[:4]):04d}0000"[:13],
        phone_verified_at=datetime.now(timezone.utc),
    )
    session.add(cprofile)
    await session.flush()
    assert cprofile.id is not None

    seller_user = User(email=f"sell-{label}-{tag}@x.test", role=UserRole.Seller, is_active=True)
    session.add(seller_user)
    await session.flush()
    assert seller_user.id is not None
    seller = SellerProfile(
        user_id=seller_user.id, first_name="Anil",
        phone=f"+9177{int(tag[:4]):04d}0000"[:13],
        business_name="Anil Stores",
        verification_status=VerificationStatus.Approved,
        business_address_id=await _address(session, "1 Biz Rd"),
    )
    session.add(seller)
    await session.flush()
    assert seller.id is not None

    store = Store(
        name="Anil Stores", is_active=True, seller_profile_id=seller.id,
        address_id=await _address(session, "2 Store Rd"), pin_confirmed=True,
    )
    session.add(store)
    await session.flush()
    assert store.id is not None

    service = Service(slug=f"grocery-{tag}", is_active=True, sort_order=0)
    session.add(service)
    await session.flush()
    assert service.id is not None
    session.add(
        SellerProfileService(
            seller_profile_id=seller.id, service_id=service.id,
            return_window_days=return_window_days,
        )
    )

    inventory_ids: list[int] = []
    if with_inventory:
        category = Category(service_id=service.id, slug=f"cat-{tag}")
        session.add(category)
        await session.flush()
        assert category.id is not None
        sub = Subcategory(category_id=category.id, slug=f"sub-{tag}")
        session.add(sub)
        await session.flush()
        assert sub.id is not None
        for idx, (_name, price, _qty) in enumerate(specs):
            product = MasterProduct(subcategory_id=sub.id, slug=f"p-{tag}-{idx}")
            session.add(product)
            await session.flush()
            assert product.id is not None
            inv = StoreInventory(
                store_id=store.id, product_id=product.id, price=price, stock=10,
                is_available=True,
            )
            session.add(inv)
            await session.flush()
            assert inv.id is not None
            inventory_ids.append(inv.id)

    subtotal = round(sum(price * qty for _n, price, qty in specs), 2)
    delivered_at = datetime.now(timezone.utc) - timedelta(days=delivered_days_ago)
    is_delivered = order_status == OrderStatus.Delivered
    order = Order(
        customer_profile_id=cprofile.id, store_id=store.id, service_id=service.id,
        service_name_snapshot="Grocery",
        delivery_address_id=await _address(session, "3 Home Rd"),
        status=order_status, subtotal=subtotal, delivery_fee=delivery_fee, tax=0.0,
        total=round(subtotal + delivery_fee, 2),
        delivery_address_snapshot="3 Home Rd, Pune",
    )
    session.add(order)
    await session.flush()
    assert order.id is not None

    order_item_ids: list[int] = []
    for idx, (name, price, qty) in enumerate(specs):
        item = OrderItem(
            order_id=order.id,
            inventory_id=inventory_ids[idx] if with_inventory else None,
            product_name_snapshot=name, unit_price_snapshot=price, quantity=qty,
            line_total=round(price * qty, 2),
        )
        session.add(item)
        await session.flush()
        assert item.id is not None
        order_item_ids.append(item.id)

    session.add(Payment(
        order_id=order.id, amount=order.total, method=payment_method,
        status=PaymentStatus.Paid if is_delivered else PaymentStatus.Pending,
    ))
    session.add(Delivery(
        order_id=order.id,
        status=DeliveryStatus.Delivered if is_delivered else DeliveryStatus.Pending,
        delivered_at=delivered_at if is_delivered else None,
    ))
    await session.commit()

    return SeededOrder(
        customer_user=customer, customer_profile_id=cprofile.id,
        seller_user=seller_user, seller_profile_id=seller.id, store_id=store.id,
        service_id=service.id, order_id=order.id, order_item_ids=order_item_ids,
        inventory_ids=inventory_ids, subtotal=subtotal, delivery_fee=delivery_fee,
    )


def as_customer(user: User) -> None:
    from app.core.security import get_current_customer, get_current_user

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_customer] = lambda: user


def as_seller(user: User) -> None:
    from app.core.security import get_current_seller, get_current_user

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_seller] = lambda: user


def as_admin(user: User) -> None:
    from app.core.security import get_current_admin, get_current_user

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_admin] = lambda: user


def clear_overrides() -> None:
    from app.core.security import (
        get_current_admin,
        get_current_customer,
        get_current_seller,
        get_current_user,
    )

    for dep in (get_current_user, get_current_customer, get_current_seller, get_current_admin):
        app.dependency_overrides.pop(dep, None)
