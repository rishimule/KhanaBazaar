# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.admin_audit import AdminActionLog, AdminActionTargetType
from app.models.base import User
from app.models.returns import (
    CustomerStoreCredit,
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
)
from tests._returns_helpers import (
    as_admin,
    clear_overrides,
    pk,
    publish_return_agreement,
    seed_delivered_order,
)


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    clear_overrides()


async def _active_return(
    session: AsyncSession,
    seed: Any,
    *,
    status: ReturnStatus = ReturnStatus.active,
    choice: ReturnSettlementChoice = ReturnSettlementChoice.store_credit,
) -> ReturnRequest:
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user_id, status=status,
        is_full_order=False, reason_code=ReturnReasonCode.damaged,
        items_amount=250.0, delivery_fee_amount=0.0, total_amount=250.0,
        payment_amount=250.0 if status == ReturnStatus.awaiting_payment_confirmation else 0.0,
        settlement_choice=choice, agreement_policy_version=1,
        window_expires_at=now + timedelta(days=5),
        confirm_expires_at=now + timedelta(hours=48),
        handover_expires_at=now + timedelta(days=7),
        receipt_otp="111222" if status == ReturnStatus.active else None,
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


async def test_admin_initiated_return_still_awaits_the_customer(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    """Admin authority resolves stuck returns; it never manufactures consent."""
    seed = await seed_delivered_order(session)
    await publish_return_agreement(session)
    as_admin(admin_user)

    resp = await client.post(
        "/api/v1/admin/returns",
        json={
            "order_id": seed.order_id,
            "order_item_ids": [seed.order_item_ids[0]],
            "reason_code": "damaged",
            "settlement_choice": "store_credit",
            "customer_profile_id": seed.customer_profile_id,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "awaiting_customer_confirmation"
    assert resp.json()["initiated_by"] == "admin"


async def test_force_accept_without_otp_closes_and_audits(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/accept",
        json={"reason": "seller unreachable for six days", "restock": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "closed"

    acct = (await session.exec(select(CustomerStoreCredit))).first()
    assert acct is not None
    assert acct.balance == 250.0

    logs = (await session.exec(select(AdminActionLog))).all()
    assert len(logs) == 1
    assert logs[0].action == "return.force_accept"
    assert logs[0].target_type == AdminActionTargetType.Return
    assert logs[0].target_id == pk(req.id)
    assert logs[0].reason == "seller unreachable for six days"


async def test_force_accept_rejects_a_short_reason_and_writes_no_audit(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    """No audit row on rejection proves the row is inside the same transaction."""
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/accept",
        json={"reason": "too short", "restock": False},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "reason_required"
    assert (await session.exec(select(AdminActionLog))).all() == []

    session.expunge_all()
    row = await session.get(ReturnRequest, pk(req.id))
    assert row is not None
    assert row.status == ReturnStatus.active


async def test_force_reject_audits_with_the_reason(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/reject",
        json={"reason": "goods were never handed over"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    logs = (await session.exec(select(AdminActionLog))).all()
    assert logs[0].action == "return.force_reject"
    assert logs[0].reason == "goods were never handed over"


async def test_force_close_moves_a_stuck_return_to_closed(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(
        session, seed, status=ReturnStatus.awaiting_payment_confirmation
    )
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/close",
        json={"reason": "cash settled at the counter, customer went quiet"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"

    logs = (await session.exec(select(AdminActionLog))).all()
    assert logs[0].action == "return.force_close"


async def test_force_close_on_a_terminal_return_is_refused(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed, status=ReturnStatus.closed)
    as_admin(admin_user)

    resp = await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/close",
        json={"reason": "trying to close an already closed return"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "illegal_return_transition"


async def test_admin_list_filters_by_seller(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    one = await seed_delivered_order(session, email_suffix="one")
    two = await seed_delivered_order(session, email_suffix="two")
    await _active_return(session, one)
    await _active_return(session, two)
    as_admin(admin_user)

    everything = (await client.get("/api/v1/admin/returns")).json()
    assert len(everything) == 2

    filtered = (
        await client.get(f"/api/v1/admin/returns?seller_id={one.seller_profile_id}")
    ).json()
    assert len(filtered) == 1
    assert filtered[0]["seller_profile_id"] == one.seller_profile_id


async def test_admin_seller_hub_listing(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_admin(admin_user)

    # Keyed by the seller's USER id, like every other /admin/sellers route.
    body = (
        await client.get(f"/api/v1/admin/sellers/{seed.seller_user_id}/returns")
    ).json()
    assert [r["id"] for r in body] == [pk(req.id)]


async def test_admin_detail_is_readable(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    seed = await seed_delivered_order(session)
    req = await _active_return(session, seed)
    as_admin(admin_user)

    body = (await client.get(f"/api/v1/admin/returns/{pk(req.id)}")).json()
    assert body["id"] == pk(req.id)
    assert body["total_amount"] == 250.0


async def test_force_accept_can_restock(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    from app.models.store import StoreInventory

    seed = await seed_delivered_order(session, with_inventory=True)
    req = await _active_return(session, seed)
    as_admin(admin_user)

    await client.post(
        f"/api/v1/admin/returns/{pk(req.id)}/accept",
        json={"reason": "seller confirmed receipt by phone", "restock": True},
    )
    session.expunge_all()
    inv = await session.get(StoreInventory, seed.inventory_ids[0])
    assert inv is not None
    assert inv.stock == 11


async def test_admin_seller_hub_listing_404s_for_an_unknown_seller(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    await seed_delivered_order(session)
    as_admin(admin_user)
    resp = await client.get("/api/v1/admin/sellers/999999/returns")
    assert resp.status_code == 404


async def test_admin_can_view_customer_store_credit(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    from app.models.returns import StoreCreditEntryType
    from app.services import customer_store_credit as credit_svc

    seed = await seed_delivered_order(session)
    account = await credit_svc.get_or_create_account(
        session, seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
    )
    await credit_svc.grant(
        session, account, 175.0, entry_type=StoreCreditEntryType.return_credit
    )
    await session.commit()
    as_admin(admin_user)

    body = (
        await client.get(
            f"/api/v1/admin/customers/{seed.customer_profile_id}/store-credit"
        )
    ).json()
    assert body[0]["balance"] == 175.0
    assert body[0]["store_name"] == "Anil Stores"


async def test_admin_store_credit_is_empty_for_a_customer_without_any(
    session: AsyncSession, client: AsyncClient, admin_user: User
) -> None:
    seed = await seed_delivered_order(session)
    as_admin(admin_user)
    body = (
        await client.get(
            f"/api/v1/admin/customers/{seed.customer_profile_id}/store-credit"
        )
    ).json()
    assert body == []
