# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""The agreement version recorded on a return is the one accepted at confirmation."""
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.otp import hash_code
from app.core.redis import get_redis
from app.models.consent import PolicyDocument, PolicyKind
from app.models.returns import ReturnRequest
from tests._returns_helpers import (
    SeededOrder,
    as_customer,
    clear_overrides,
    publish_return_agreement,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _create(client: AsyncClient, seed: SeededOrder) -> int:
    resp = await client.post("/api/v1/returns", json={
        "order_id": seed.order_id, "order_item_ids": seed.order_item_ids[:1],
        "reason_code": "damaged", "settlement_choice": "store_credit",
    })
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


async def _seed_code(seed: SeededOrder, return_id: int) -> None:
    redis = await get_redis()
    await redis.hset(  # type: ignore[misc]
        f"otp:return_initiate:code:{seed.customer_user_id}:{return_id}",
        mapping={"code_hash": hash_code("424242"), "attempts": "0"},
    )


async def _confirm(client: AsyncClient, return_id: int) -> Any:
    return await client.post(
        f"/api/v1/returns/{return_id}/confirm",
        json={"otp": "424242", "agreement_accepted": True},
    )


async def test_confirmation_stamps_the_current_agreement_version(
    session: AsyncSession, client: AsyncClient
) -> None:
    """A seller-started return can wait days; the terms may change meanwhile."""
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session, version=1)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await publish_return_agreement(session, version=2)
    await _seed_code(seed, rid)

    resp = await _confirm(client, rid)

    assert resp.status_code == 200, resp.text
    assert resp.json()["agreement_policy_version"] == 2
    session.expunge_all()
    row = await session.get(ReturnRequest, rid)
    assert row is not None and row.agreement_policy_version == 2


async def test_confirmation_without_an_agreement_keeps_the_code_usable(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session, version=1)
    as_customer(seed.customer_user)
    rid = await _create(client, seed)
    await session.exec(
        delete(PolicyDocument).where(
            PolicyDocument.kind == PolicyKind.return_agreement  # type: ignore[arg-type]
        )
    )
    await session.commit()
    await _seed_code(seed, rid)

    refused = await _confirm(client, rid)
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "agreement_unavailable"

    await publish_return_agreement(session, version=3)
    resp = await _confirm(client, rid)

    assert resp.status_code == 200, resp.text
    assert resp.json()["agreement_policy_version"] == 3
