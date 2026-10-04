# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import OrderStatus
from app.models.notification import Notification
from app.models.profile import SellerProfile
from app.utils.delivery_window import ist_today
from tests._courier_helpers import (
    ADMIN,
    CUSTOMER,
    SELLER,
    CourierWorld,
    accept_quote,
    claim_payment,
    client_as,
    confirm_payment,
    get_order,
    insert_courier_order,
    place_courier_order,
    seed_courier_world,
    send_quote,
)


async def _accepted(world: CourierWorld) -> int:
    order = await place_courier_order(world)
    quote = (await send_quote(order["id"])).json()["courier"]["quotes"][0]
    assert (await accept_quote(order["id"], quote["id"])).status_code == 200
    return int(order["id"])


async def _statuses(session: AsyncSession, order_id: int) -> list[str]:
    rows = (await session.exec(select(Notification).where(Notification.order_id == order_id))).all()
    return [r.status_value for r in rows]


async def test_claim_records_the_method_and_tells_the_seller_once(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    first = await claim_payment(order_id, "net_banking")
    again = await claim_payment(order_id, "net_banking")
    assert first.status_code == 200, first.text
    payment = again.json()["payment"]
    assert payment["method"] == "net_banking" and payment["customer_claimed_at"] is not None
    assert payment["status"] == "pending"
    assert (await _statuses(session, order_id)).count("courier_payment_claimed") == 1


async def test_switching_method_after_claiming_is_silent(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    assert (await claim_payment(order_id, "upi")).status_code == 200
    switched = await claim_payment(order_id, "net_banking")
    assert switched.status_code == 200, switched.text
    assert switched.json()["payment"]["method"] == "net_banking"
    assert (await _statuses(session, order_id)).count("courier_payment_claimed") == 1


async def test_claim_rules(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order = await place_courier_order(world)
    quoted = (await send_quote(order["id"])).json()
    too_early = await claim_payment(order["id"], "upi")
    assert too_early.status_code == 409 and too_early.json()["detail"] == "not_awaiting_payment"
    await accept_quote(order["id"], quoted["courier"]["quotes"][0]["id"])
    no_method = await claim_payment(order["id"], None)
    cash = await claim_payment(order["id"], "cash")
    assert no_method.status_code == 422 and no_method.json()["detail"] == "payment_method_required"
    assert cash.status_code == 422 and cash.json()["detail"] == "payment_method_not_allowed"
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    seller.upi_enabled = False
    await session.commit()
    dead = await claim_payment(order["id"], "upi")
    assert dead.status_code == 409 and dead.json()["detail"] == "upi_unavailable"


async def test_claim_with_no_payee_left_tells_the_seller(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    seller.upi_enabled = False
    seller.bank_transfer_enabled = False
    await session.commit()
    resp = await claim_payment(order_id, "upi")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "courier_payment_unavailable"
    assert "courier_payee_missing" in await _statuses(session, order_id)


async def test_seller_confirms_even_before_a_claim(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    resp = await confirm_payment(order_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "paid" and body["payment"]["status"] == "paid"
    today = ist_today()
    assert body["courier"]["eta_from"] == (today + timedelta(days=3)).isoformat()
    assert body["courier"]["eta_to"] == (today + timedelta(days=5)).isoformat()
    assert "courier_payment_confirmed" in await _statuses(session, order_id)
    again = await confirm_payment(order_id)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "payment_settled"


async def test_payment_not_received_clears_the_claim(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    await claim_payment(order_id, "upi")
    async with client_as(SELLER) as ac:
        resp = await ac.post(
            f"/api/v1/orders/{order_id}/payment/not-received", json={"note": "got ₹300 of ₹320"},
        )
    assert resp.status_code == 200, resp.text
    customer_view = await get_order(order_id)
    assert customer_view["payment"]["customer_claimed_at"] is None
    assert customer_view["courier"]["payment_claim_rejected_note"] == "got ₹300 of ₹320"
    assert "courier_payment_not_received" in await _statuses(session, order_id)
    await claim_payment(order_id, "upi")
    assert (await get_order(order_id))["courier"]["payment_claim_rejected_at"] is None


async def test_not_received_needs_a_claim(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    async with client_as(SELLER) as ac:
        resp = await ac.post(f"/api/v1/orders/{order_id}/payment/not-received")
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "no_claim"


async def test_only_the_owning_seller_confirms(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id = await _accepted(world)
    assert (await confirm_payment(order_id, as_user=CUSTOMER)).status_code == 403
    assert (await confirm_payment(order_id, as_user=ADMIN)).status_code == 403


async def test_dashboard_counts_claims_waiting_on_the_seller(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await insert_courier_order(session, world, status=OrderStatus.Accepted, claimed=True)
    # Accepted but not claimed: the customer's turn, not the seller's.
    await insert_courier_order(session, world, status=OrderStatus.Accepted)
    async with client_as(SELLER) as ac:
        resp = await ac.get("/api/v1/sellers/me/metrics")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["courier_payment_checks"] == 1
    assert body["order_status_counts"]["accepted"] == 2
