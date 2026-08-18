# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.redis import get_redis
from app.models.returns import ReturnEvent, ReturnRequestItem, ReturnStatus
from tests._returns_helpers import (
    as_customer,
    clear_overrides,
    publish_return_agreement,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


def _body(seed: Any, item_ids: Any = None, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "order_id": seed.order_id,
        "order_item_ids": item_ids if item_ids is not None else seed.order_item_ids,
        "reason_code": "damaged",
        "settlement_choice": "store_credit",
    }
    payload.update(overrides)
    return payload


async def test_full_order_return_includes_the_delivery_fee(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    resp = await client.post("/api/v1/returns", json=_body(seed))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "awaiting_customer_confirmation"
    assert body["is_full_order"] is True
    assert body["items_amount"] == 850.0
    assert body["delivery_fee_amount"] == 20.0
    assert body["total_amount"] == 870.0
    assert body["initiated_by"] == "customer"


async def test_partial_return_excludes_the_delivery_fee(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    resp = await client.post(
        "/api/v1/returns", json=_body(seed, item_ids=[seed.order_item_ids[0]])
    )
    body = resp.json()
    assert body["is_full_order"] is False
    assert body["delivery_fee_amount"] == 0.0
    assert body["total_amount"] == 250.0


async def test_creation_writes_items_and_an_event(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    rid = (await client.post("/api/v1/returns", json=_body(seed))).json()["id"]

    items = (await session.exec(
        select(ReturnRequestItem).where(ReturnRequestItem.return_request_id == rid)
    )).all()
    assert len(items) == 2
    assert items[0].product_name_snapshot == "Ghee 1L"

    events = (await session.exec(
        select(ReturnEvent).where(ReturnEvent.return_request_id == rid)
    )).all()
    assert len(events) == 1
    assert events[0].from_status is None
    assert events[0].to_status == ReturnStatus.awaiting_customer_confirmation
    assert events[0].actor_role == "customer"


async def test_creation_stores_an_otp_in_redis(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    rid = (await client.post("/api/v1/returns", json=_body(seed))).json()["id"]

    redis = await get_redis()
    key = f"otp:return_initiate:code:{seed.customer_user.id}:{rid}"
    assert await redis.hget(key, "code_hash") is not None


async def test_creation_without_a_published_agreement_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    as_customer(seed.customer_user)

    resp = await client.post("/api/v1/returns", json=_body(seed))
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "agreement_unavailable"


async def test_locked_line_cannot_be_selected_again(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    first = await client.post(
        "/api/v1/returns", json=_body(seed, item_ids=[seed.order_item_ids[0]])
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/returns", json=_body(seed, item_ids=[seed.order_item_ids[0]])
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "items_already_returned"


async def test_second_return_can_take_the_remaining_line(
    session: AsyncSession, client: AsyncClient
) -> None:
    """One order, two returns — the BRD allows a second defect found later."""
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    first = await client.post(
        "/api/v1/returns", json=_body(seed, item_ids=[seed.order_item_ids[0]])
    )
    second = await client.post(
        "/api/v1/returns", json=_body(seed, item_ids=[seed.order_item_ids[1]])
    )
    assert first.status_code == 201
    assert second.status_code == 201
    # Neither is a full-order return, so neither returns the delivery fee.
    assert first.json()["delivery_fee_amount"] == 0.0
    assert second.json()["delivery_fee_amount"] == 0.0


async def test_empty_selection_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    resp = await client.post("/api/v1/returns", json=_body(seed, item_ids=[]))
    assert resp.status_code == 422


async def test_line_from_another_order_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, email_suffix="a")
    other = await seed_delivered_order(session, email_suffix="b")
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    resp = await client.post(
        "/api/v1/returns", json=_body(seed, item_ids=[other.order_item_ids[0]])
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "invalid_order_item"


async def test_closed_window_blocks_creation(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, delivered_days_ago=30, return_window_days=7)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    resp = await client.post("/api/v1/returns", json=_body(seed))
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "return_window_closed"


async def test_reason_other_requires_a_note(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    resp = await client.post("/api/v1/returns", json=_body(seed, reason_code="other"))
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "reason_note_required"

    ok = await client.post(
        "/api/v1/returns",
        json=_body(seed, reason_code="other", reason_note="Seal was broken"),
    )
    assert ok.status_code == 201


async def test_duplicate_item_ids_are_deduped(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    rid = (await client.post(
        "/api/v1/returns",
        json=_body(seed, item_ids=[seed.order_item_ids[0], seed.order_item_ids[0]]),
    )).json()["id"]

    items = (await session.exec(
        select(ReturnRequestItem).where(ReturnRequestItem.return_request_id == rid)
    )).all()
    assert len(items) == 1


async def test_resend_is_cooldown_limited(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)

    rid = (await client.post("/api/v1/returns", json=_body(seed))).json()["id"]
    resp = await client.post(f"/api/v1/returns/{rid}/otp/resend")
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "resend_cooldown"
    assert resp.json()["detail"]["retry_after"] > 0
