# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import (
    ACTIVE_ORDER_STATUSES,
    DeliveryMode,
    Order,
    OrderStatus,
    Payment,
)
from app.models.courier import CourierQuote, OrderCourier
from app.models.notification import NotificationType
from app.models.profile import CustomerAddress, SellerProfile, SellerProfileService
from app.models.store import Store
from tests._courier_helpers import (
    OTHER_SELLER,
    SELLER,
    CourierWorld,
    seed_courier_world,
)


def test_new_members_keep_legacy_pascalcase_names() -> None:
    # Postgres stores the member NAME; these enums use PascalCase names.
    assert (DeliveryMode.Courier.name, DeliveryMode.Courier.value) == ("Courier", "courier")
    assert (OrderStatus.Quoted.name, OrderStatus.Quoted.value) == ("Quoted", "quoted")
    assert (OrderStatus.Accepted.name, OrderStatus.Accepted.value) == ("Accepted", "accepted")
    assert NotificationType.SellerOrderUpdate.value == "seller_order_update"


def test_active_statuses_are_every_non_terminal_status() -> None:
    terminal = {OrderStatus.Delivered, OrderStatus.Cancelled}
    assert set(ACTIVE_ORDER_STATUSES) == set(OrderStatus) - terminal
    assert len(ACTIVE_ORDER_STATUSES) == len(set(ACTIVE_ORDER_STATUSES))


async def _bare_courier_order(session: AsyncSession, world: CourierWorld) -> int:
    link = await session.get(CustomerAddress, world.courier_address_id)
    assert link is not None
    order = Order(
        customer_profile_id=world.customer_profile_id,
        store_id=world.store_id,
        service_id=world.service_id,
        service_name_snapshot="Sweets",
        delivery_address_id=link.address_id,
        delivery_address_snapshot="Mysuru 570001",
        delivery_mode=DeliveryMode.Courier,
        status=OrderStatus.Quoted,
        subtotal=200.0,
        delivery_fee=0.0,
        tax=0.0,
        total=200.0,
    )
    session.add(order)
    await session.commit()
    assert order.id is not None
    return order.id


async def test_courier_order_round_trips_new_enum_values(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _bare_courier_order(session, world)
    session.expire_all()
    order = await session.get(Order, order_id)
    assert order is not None
    assert order.delivery_mode is DeliveryMode.Courier
    assert order.status is OrderStatus.Quoted


async def test_new_columns_default_off(session: AsyncSession) -> None:
    world = await seed_courier_world(session, courier_radius_km=None, courier_enabled=False)
    store = await session.get(Store, world.store_id)
    assert store is not None and store.courier_radius_km is None
    sps = await session.get(SellerProfileService, world.sps_id)
    assert sps is not None and sps.courier_enabled is False
    other = (
        await session.exec(select(SellerProfile).where(SellerProfile.user_id == OTHER_SELLER.id))
    ).one()
    assert other.bank_transfer_enabled is False
    assert other.bank_account_name is None


async def test_quote_versions_are_unique_per_order(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _bare_courier_order(session, world)
    session.add(CourierQuote(
        order_id=order_id, version=1, courier_fee=120.0,
        eta_min_days=3, eta_max_days=5, created_by_user_id=SELLER.id,
    ))
    await session.commit()
    session.add(CourierQuote(
        order_id=order_id, version=1, courier_fee=90.0,
        eta_min_days=2, eta_max_days=4, created_by_user_id=SELLER.id,
    ))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_one_courier_row_per_order(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _bare_courier_order(session, world)
    session.add(OrderCourier(order_id=order_id, recipient_name="Asha", recipient_phone="+919900000001"))
    await session.commit()
    session.add(OrderCourier(order_id=order_id, recipient_name="Again", recipient_phone="+919900000009"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_order_courier_defaults(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _bare_courier_order(session, world)
    row = OrderCourier(order_id=order_id, recipient_name="Asha", recipient_phone="+919900000001")
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.apply_store_credit is True
    assert row.payment_claim_rejection_count == 0
    for attr in (
        "accepted_quote_id", "accepted_at", "eta_from", "eta_to",
        "payment_claim_rejected_at", "payment_claim_rejected_note",
        "carrier_name", "tracking_number", "tracking_url", "tracking_updated_at",
        "delivered_by", "cancel_reason", "cancelled_by", "cancelled_at",
        "payment_reported_missing_at", "last_reminder_key", "last_reminder_at",
    ):
        assert getattr(row, attr) is None, attr


async def test_payment_refund_columns_default_none(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _bare_courier_order(session, world)
    payment = Payment(order_id=order_id, amount=200.0)
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    assert payment.refunded_at is None
    assert payment.refund_reference is None
    assert payment.refunded_by_user_id is None
