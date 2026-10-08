# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Payment methods at checkout and the payee saved on each order
(spec 2026-10-07 §5–§7)."""
from typing import Any

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Payment
from app.models.profile import SellerProfile, SellerProfileService
from tests._courier_helpers import (
    CUSTOMER,
    CourierWorld,
    client_as,
    place_courier_order,
    seed_courier_world,
)


async def _place_local(
    world: CourierWorld, method: str = "upi", mode: str = "door_delivery"
) -> httpx.Response:
    body: dict[str, Any] = {
        "store_id": world.store_id, "service_id": world.service_id,
        "payment_method": method, "delivery_mode": mode,
    }
    if mode == "door_delivery":
        body["customer_address_id"] = world.local_address_id
    async with client_as(CUSTOMER) as ac:
        return await ac.post("/api/v1/orders", json=body)


async def _payment(session: AsyncSession, order_id: int) -> Payment:
    payment = (await session.exec(select(Payment).where(Payment.order_id == order_id))).first()
    assert payment is not None
    await session.refresh(payment)
    return payment


async def _set(session: AsyncSession, world: CourierWorld, **fields: Any) -> None:
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    await session.refresh(seller)
    for name, value in fields.items():
        setattr(seller, name, value)
    session.add(seller)
    await session.commit()


async def _enable_pickup(session: AsyncSession, world: CourierWorld) -> None:
    sps = await session.get(SellerProfileService, world.sps_id)
    assert sps is not None
    sps.pickup_enabled = True
    session.add(sps)
    await session.commit()


async def test_a_switched_off_cash_is_refused_at_checkout(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _set(session, world, cod_enabled=False)
    r = await _place_local(world, "cash")
    assert (r.status_code, r.json()["detail"]) == (409, "cash_unavailable")


async def test_a_switched_off_pay_at_store_refuses_pickup(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _enable_pickup(session, world)
    await _set(session, world, pay_at_store_enabled=False)
    r = await _place_local(world, "pay_at_store", "pickup")
    assert (r.status_code, r.json()["detail"]) == (409, "pay_at_store_unavailable")


async def test_local_bank_transfer_needs_live_details(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _set(session, world, bank_transfer_enabled=False)
    r = await _place_local(world, "net_banking")
    assert (r.status_code, r.json()["detail"]) == (409, "bank_transfer_unavailable")


async def test_a_local_upi_order_saves_only_the_upi_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    r = await _place_local(world, "upi")
    assert r.status_code == 201, r.text
    p = await _payment(session, r.json()["id"])
    assert (p.payee_upi_vpa, p.payee_upi_name, p.payee_upi_generation) == (
        "ravi@okaxis", "Ravi Sweets", 0,
    )
    assert p.payee_bank_account_number is None


async def test_a_local_bank_order_saves_only_the_bank_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    r = await _place_local(world, "net_banking")
    assert r.status_code == 201, r.text
    p = await _payment(session, r.json()["id"])
    assert (p.payee_bank_account_name, p.payee_bank_account_number, p.payee_bank_ifsc) == (
        "Ravi Sweets", "123456789012", "HDFC0001234",
    )
    assert p.payee_upi_vpa is None


async def test_a_cash_order_saves_no_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    r = await _place_local(world, "cash")
    assert r.status_code == 201, r.text
    p = await _payment(session, r.json()["id"])
    assert p.payee_upi_vpa is None and p.payee_bank_account_number is None


async def test_a_courier_order_saves_every_live_prepaid_payee(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    p = await _payment(session, order["id"])
    assert p.payee_upi_vpa == "ravi@okaxis"
    assert p.payee_bank_account_number == "123456789012"


async def test_store_read_offers_only_live_methods(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await _set(session, world, bank_transfer_enabled=False, pay_at_store_enabled=False)
    async with client_as(CUSTOMER) as ac:
        body = (await ac.get(f"/api/v1/stores/{world.store_id}")).json()
    assert body["accepted_payment_methods"] == ["upi", "cash"]
    assert body["bank_transfer_payee"] is None
    await _set(session, world, bank_transfer_enabled=True)
    async with client_as(CUSTOMER) as ac:
        body = (await ac.get(f"/api/v1/stores/{world.store_id}")).json()
    assert body["bank_transfer_payee"] == {"account_name": "Ravi Sweets"}
    assert "account_number" not in body["bank_transfer_payee"]
