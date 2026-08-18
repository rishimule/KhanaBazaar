# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.returns import (
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
    StoreCreditEntryType,
)
from app.services import customer_store_credit as credit_svc
from tests._returns_helpers import (
    as_customer,
    as_seller,
    clear_overrides,
    pk,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _active_return(
    session: AsyncSession, seed: Any, *, code: str = "111222"
) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id, status=ReturnStatus.active,
        is_full_order=False, reason_code=ReturnReasonCode.damaged,
        items_amount=250.0, delivery_fee_amount=0.0, total_amount=250.0,
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1, window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
        handover_expires_at=now + timedelta(days=7),
        receipt_otp=code, receipt_otp_sent_at=now,
    )
    session.add(req)
    await session.flush()
    session.add(ReturnRequestItem(
        return_request_id=req.id, order_item_id=seed.order_item_ids[0],
        quantity=1, product_name_snapshot="Ghee 1L", unit_price_snapshot=250.0,
        line_total=250.0,
    ))
    await session.commit()
    await session.refresh(req)
    return req


async def test_customer_sees_only_their_returns(
    session: AsyncSession, client: AsyncClient
) -> None:
    mine = await seed_delivered_order(session, email_suffix="mine")
    theirs = await seed_delivered_order(session, email_suffix="theirs")
    my_req = await _active_return(session, mine)
    await _active_return(session, theirs)
    as_customer(mine.customer_user)

    body = (await client.get("/api/v1/returns")).json()
    assert [r["id"] for r in body] == [pk(my_req.id)]


async def test_customer_detail_exposes_the_receipt_code_while_active(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_customer(seed.customer_user)

    body = (await client.get(f"/api/v1/returns/{pk(req.id)}")).json()
    assert body["receipt_otp"] == "111222"
    assert body["items"][0]["product_name"] == "Ghee 1L"


async def test_customer_list_hides_the_code_once_terminal(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    req.status = ReturnStatus.closed
    session.add(req)
    await session.commit()
    as_customer(seed.customer_user)

    body = (await client.get("/api/v1/returns")).json()
    assert body[0]["receipt_otp"] is None


async def test_seller_detail_never_exposes_the_receipt_code(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The seller types what the customer shows; handing them the code in a
    payload would defeat the point of the handover check."""
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_seller(seed.seller_user)

    body = (await client.get(f"/api/v1/sellers/me/returns/{pk(req.id)}")).json()
    assert body["receipt_otp"] is None


async def test_seller_list_never_exposes_the_receipt_code(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await _active_return(session, seed)
    as_seller(seed.seller_user)

    body = (await client.get("/api/v1/sellers/me/returns")).json()
    assert body[0]["receipt_otp"] is None


async def test_seller_sees_only_their_own_returns(
    session: AsyncSession, client: AsyncClient
) -> None:
    mine = await seed_delivered_order(session, email_suffix="mine")
    theirs = await seed_delivered_order(session, email_suffix="theirs")
    await _active_return(session, mine)
    await _active_return(session, theirs)
    as_seller(mine.seller_user)

    body = (await client.get("/api/v1/sellers/me/returns")).json()
    assert len(body) == 1
    assert body[0]["seller_profile_id"] == mine.seller_profile_id


async def test_status_filter_narrows_the_queue(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await _active_return(session, seed)
    as_seller(seed.seller_user)

    active = (await client.get("/api/v1/sellers/me/returns?status=active")).json()
    closed = (await client.get("/api/v1/sellers/me/returns?status=closed")).json()
    assert len(active) == 1
    assert closed == []


async def test_store_credit_balances_and_ledger(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    account = await credit_svc.get_or_create_account(
        session, seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
    )
    await credit_svc.grant(
        session, account, 250.0, entry_type=StoreCreditEntryType.return_credit
    )
    await session.commit()
    as_customer(seed.customer_user)

    balances = (await client.get("/api/v1/store-credit")).json()
    assert balances[0]["balance"] == 250.0
    assert balances[0]["seller_profile_id"] == seed.seller_profile_id
    assert balances[0]["store_name"] == "Anil Stores"
    assert balances[0]["lifetime_earned"] == 250.0

    ledger = (
        await client.get(f"/api/v1/store-credit/{seed.seller_profile_id}/ledger")
    ).json()
    assert ledger[0]["entry_type"] == "return_credit"
    assert ledger[0]["amount"] == 250.0
    assert ledger[0]["balance_after"] == 250.0


async def test_ledger_of_another_customer_is_empty_not_leaked(
    session: AsyncSession, client: AsyncClient
) -> None:
    owner = await seed_delivered_order(session, email_suffix="owner")
    account = await credit_svc.get_or_create_account(
        session, seller_profile_id=owner.seller_profile_id,
        customer_profile_id=owner.customer_profile_id,
    )
    await credit_svc.grant(
        session, account, 99.0, entry_type=StoreCreditEntryType.return_credit
    )
    await session.commit()

    other = await seed_delivered_order(session, email_suffix="other")
    as_customer(other.customer_user)
    ledger = (
        await client.get(f"/api/v1/store-credit/{owner.seller_profile_id}/ledger")
    ).json()
    assert ledger == []


async def test_customer_with_no_credit_gets_an_empty_list(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    as_customer(seed.customer_user)
    assert (await client.get("/api/v1/store-credit")).json() == []
