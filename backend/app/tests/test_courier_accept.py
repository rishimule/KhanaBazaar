# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import timedelta
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.notification import Notification
from app.models.profile import SellerProfile
from app.utils.delivery_window import ist_today
from tests._courier_helpers import (
    SELLER,
    CourierWorld,
    accept_quote,
    get_order,
    grant_store_credit,
    place_courier_order,
    seed_courier_world,
    send_quote,
)


async def _quoted(world: CourierWorld, *, fee: float = 120.0, **place: Any) -> tuple[int, int]:
    order = await place_courier_order(world, **place)
    quote = (await send_quote(order["id"], fee=fee)).json()["courier"]["quotes"][0]
    return order["id"], quote["id"]


async def _statuses(session: AsyncSession, order_id: int) -> list[str]:
    rows = (await session.exec(select(Notification).where(Notification.order_id == order_id))).all()
    return [r.status_value for r in rows]


async def test_accept_fixes_the_charge_and_waits_for_payment(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id, quote_id = await _quoted(world)
    resp = await accept_quote(order_id, quote_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "accepted"
    assert (body["delivery_fee"], body["total"], body["payment"]["amount"]) == (120.0, 320.0, 320.0)
    assert body["courier"]["accepted_quote_id"] == quote_id
    assert body["courier"]["payable_methods"] == ["upi", "net_banking"]
    assert body["courier"]["bank_transfer"] == {
        "account_name": "Ravi Sweets", "account_number": "123456789012", "ifsc": "HDFC0001234",
    }
    assert "courier_accepted" in await _statuses(session, order_id)


async def test_bank_details_reach_only_the_customer_and_only_while_accepted(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id, quote_id = await _quoted(world)
    assert (await get_order(order_id))["courier"]["bank_transfer"] is None  # still quoted
    await accept_quote(order_id, quote_id)
    assert (await get_order(order_id))["courier"]["bank_transfer"] is not None
    assert (await get_order(order_id, as_user=SELLER))["courier"]["bank_transfer"] is None


async def test_superseded_quote_is_rejected(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id, first_id = await _quoted(world, fee=120.0)
    second = (await send_quote(order_id, fee=150.0)).json()["courier"]["quotes"][0]
    stale = await accept_quote(order_id, first_id)
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "quote_superseded"
    fresh = await accept_quote(order_id, second["id"])
    assert fresh.status_code == 200 and fresh.json()["total"] == 350.0


async def test_accept_is_idempotent(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id, quote_id = await _quoted(world)
    assert (await accept_quote(order_id, quote_id)).status_code == 200
    again = await accept_quote(order_id, quote_id)
    assert again.status_code == 200 and again.json()["status"] == "accepted"
    assert (await _statuses(session, order_id)).count("courier_accepted") == 1


async def test_quote_is_locked_after_acceptance(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id, quote_id = await _quoted(world)
    await accept_quote(order_id, quote_id)
    resp = await send_quote(order_id, fee=200.0)
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "quote_locked"


async def test_store_credit_tops_up_the_courier_charge(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await grant_store_credit(session, world, 250.0)
    order_id, quote_id = await _quoted(world)  # goods 200 → all 200 from credit
    body = (await accept_quote(order_id, quote_id)).json()
    assert body["store_credit_applied"] == 250.0  # 200 at placement + 50 top-up
    assert body["payment"]["amount"] == 70.0
    assert body["status"] == "accepted"


async def test_full_coverage_auto_pays(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await grant_store_credit(session, world, 400.0)
    order_id, quote_id = await _quoted(world)
    body = (await accept_quote(order_id, quote_id)).json()
    assert body["status"] == "paid"
    assert (body["payment"]["status"], body["payment"]["amount"]) == ("paid", 0.0)
    today = ist_today()
    assert body["courier"]["eta_from"] == (today + timedelta(days=3)).isoformat()
    assert body["courier"]["eta_to"] == (today + timedelta(days=5)).isoformat()
    statuses = await _statuses(session, order_id)
    assert "courier_auto_paid" in statuses and "courier_accepted_paid" in statuses


async def test_opting_out_of_store_credit_skips_the_top_up(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    await grant_store_credit(session, world, 250.0)
    order_id, quote_id = await _quoted(world, apply_store_credit=False)
    body = (await accept_quote(order_id, quote_id)).json()
    assert body["store_credit_applied"] == 0.0
    assert body["payment"]["amount"] == 320.0


async def test_no_live_payee_blocks_acceptance_and_tells_the_seller_once(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id, quote_id = await _quoted(world)
    seller = await session.get(SellerProfile, world.seller_profile_id)
    assert seller is not None
    seller.upi_enabled = False
    seller.bank_transfer_enabled = False
    await session.commit()
    for _ in range(2):
        resp = await accept_quote(order_id, quote_id)
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "courier_payment_unavailable"
    assert (await get_order(order_id))["status"] == "quoted"
    assert (await _statuses(session, order_id)).count("courier_payee_missing") == 1


async def test_only_the_customer_accepts(session: AsyncSession) -> None:
    world = await seed_courier_world(session)
    order_id, quote_id = await _quoted(world)
    resp = await accept_quote(order_id, quote_id, as_user=SELLER)
    assert resp.status_code == 403
