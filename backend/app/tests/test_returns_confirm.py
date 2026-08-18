# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.otp import hash_code
from app.core.redis import get_redis
from app.models.returns import ReturnEvent, ReturnRequest, ReturnStatus
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


async def _create(client: AsyncClient, seed: Any, **overrides: Any) -> int:
    payload: dict[str, Any] = {
        "order_id": seed.order_id,
        "order_item_ids": seed.order_item_ids,
        "reason_code": "damaged",
        "settlement_choice": "store_credit",
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/returns", json=payload)
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


async def _known_code(user_id: int, return_id: int, code: str = "424242") -> None:
    """Overwrite the Redis OTP with a code the test knows."""
    redis = await get_redis()
    key = f"otp:return_initiate:code:{user_id}:{return_id}"
    await redis.hset(key, mapping={"code_hash": hash_code(code), "attempts": "0"})


async def test_confirm_activates_and_issues_a_receipt_code(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await _known_code(seed.customer_user.id, rid)

    resp = await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "active"
    assert body["receipt_otp"] is not None
    assert len(body["receipt_otp"]) == 6
    assert body["handover_expires_at"] is not None


async def test_confirm_records_the_transition_and_acceptance(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await _known_code(seed.customer_user.id, rid)

    await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )

    row = await session.get(ReturnRequest, rid)
    assert row is not None
    assert row.agreement_accepted_at is not None
    assert row.confirmed_at is not None
    events = (await session.exec(
        select(ReturnEvent).where(ReturnEvent.return_request_id == rid)
    )).all()
    assert [e.to_status for e in events] == [
        ReturnStatus.awaiting_customer_confirmation,
        ReturnStatus.active,
    ]


async def test_confirm_consumes_the_otp(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The code is single-use: the Redis key is dropped after a good confirm."""
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await _known_code(seed.customer_user.id, rid)

    await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )
    redis = await get_redis()
    key = f"otp:return_initiate:code:{seed.customer_user.id}:{rid}"
    assert await redis.hget(key, "code_hash") is None


async def test_wrong_code_does_not_activate(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await _known_code(seed.customer_user.id, rid)

    resp = await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "000000", "agreement_accepted": True},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "return_otp_invalid"
    row = await session.get(ReturnRequest, rid)
    assert row is not None
    assert row.status == ReturnStatus.awaiting_customer_confirmation
    assert row.receipt_otp is None


async def test_declining_the_agreement_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await _known_code(seed.customer_user.id, rid)

    resp = await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": False},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "agreement_not_accepted"


async def test_expired_confirmation_window_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await _known_code(seed.customer_user.id, rid)

    row = await session.get(ReturnRequest, rid)
    assert row is not None
    row.confirm_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.add(row)
    await session.commit()

    resp = await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "confirmation_expired"


async def test_double_confirm_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await _known_code(seed.customer_user.id, rid)
    await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )

    await _known_code(seed.customer_user.id, rid)
    resp = await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "illegal_return_transition"


async def test_withdraw_after_confirming_releases_the_lines(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await _known_code(seed.customer_user.id, rid)
    await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )

    resp = await client.post(f"/api/v1/returns/{rid}/withdraw")
    assert resp.status_code == 200
    assert resp.json()["status"] == "withdrawn"

    eligibility = (
        await client.get(f"/api/v1/returns/eligibility/{seed.order_id}")
    ).json()
    assert all(line["returnable"] for line in eligibility["lines"])
    assert eligibility["full_order_available"] is True


async def test_withdraw_clears_the_receipt_code(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await _known_code(seed.customer_user.id, rid)
    await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )
    await client.post(f"/api/v1/returns/{rid}/withdraw")

    row = await session.get(ReturnRequest, rid)
    assert row is not None
    assert row.receipt_otp is None


async def test_withdraw_from_awaiting_confirmation_is_allowed(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)

    resp = await client.post(f"/api/v1/returns/{rid}/withdraw")
    assert resp.status_code == 200
    assert resp.json()["status"] == "withdrawn"


async def test_withdraw_after_terminal_is_refused(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await client.post(f"/api/v1/returns/{rid}/withdraw")

    resp = await client.post(f"/api/v1/returns/{rid}/withdraw")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "illegal_return_transition"


async def test_another_customer_cannot_confirm(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session, email_suffix="owner")
    other = await seed_delivered_order(session, email_suffix="other")
    await publish_return_agreement(session)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await _known_code(seed.customer_user.id, rid)

    as_customer(other.customer_user)
    resp = await client.post(
        f"/api/v1/returns/{rid}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )
    assert resp.status_code == 404
