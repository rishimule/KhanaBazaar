# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import AccountStatus, User
from app.models.returns import (
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnSettlementChoice,
    ReturnStatus,
    StoreCreditEntryType,
)
from app.services import customer_store_credit as credit_svc
from tests._returns_helpers import (
    as_admin,
    as_customer,
    clear_overrides,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _return(
    session: AsyncSession, seed: Any, *, status: ReturnStatus
) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id, status=status,
        is_full_order=False, reason_code=ReturnReasonCode.damaged,
        items_amount=250.0, delivery_fee_amount=0.0, total_amount=250.0,
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1, window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def test_open_return_blocks_self_deactivate(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await _return(session, seed, status=ReturnStatus.active)
    as_customer(seed.customer_user)

    resp = await client.post("/api/v1/customers/me/deactivate", json={"reason": None})
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "open_obligations"
    assert resp.json()["detail"]["open_returns"] == 1


async def test_terminal_return_does_not_block(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await _return(session, seed, status=ReturnStatus.closed)
    as_customer(seed.customer_user)

    resp = await client.post("/api/v1/customers/me/deactivate", json={"reason": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "deactivated"


async def test_store_credit_balance_alone_does_not_block(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Credit the customer is OWED is an asset, not an obligation. It must not
    trap them in an account they want to leave."""
    seed = await seed_delivered_order(session)
    account = await credit_svc.get_or_create_account(
        session, seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
    )
    await credit_svc.grant(
        session, account, 500.0, entry_type=StoreCreditEntryType.return_credit
    )
    await session.commit()
    as_customer(seed.customer_user)

    resp = await client.post("/api/v1/customers/me/deactivate", json={"reason": None})
    assert resp.status_code == 200, resp.text


async def test_awaiting_confirmation_return_also_blocks(
    session: AsyncSession, client: AsyncClient
) -> None:
    seed = await seed_delivered_order(session)
    await _return(session, seed, status=ReturnStatus.awaiting_customer_confirmation)
    as_customer(seed.customer_user)

    resp = await client.post("/api/v1/customers/me/deactivate", json={"reason": None})
    assert resp.status_code == 409
    assert resp.json()["detail"]["open_returns"] == 1


async def test_admin_suspend_bypasses_the_guard(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    """Suspension is an abuse response — obligations must not shield an account."""
    seed = await seed_delivered_order(session)
    await _return(session, seed, status=ReturnStatus.active)
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/customers/{seed.customer_profile_id}/suspend",
        json={"reason": "chargeback abuse under investigation"},
    )
    assert resp.status_code == 200, resp.text

    session.expunge_all()
    user = await session.get(User, seed.customer_user_id)
    assert user is not None
    assert user.account_status == AccountStatus.suspended
