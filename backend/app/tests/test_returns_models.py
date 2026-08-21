# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.returns import (
    CustomerStoreCredit,
    CustomerStoreCreditEntry,
    ReturnEvent,
    ReturnInitiator,
    ReturnReasonCode,
    ReturnRequest,
    ReturnRequestItem,
    ReturnSettlementChoice,
    ReturnStatus,
    StoreCreditEntryType,
)
from tests._returns_helpers import seed_delivered_order

# pytest-asyncio runs in `auto` mode (pyproject.toml), so async tests need no
# marker and sync tests must not carry one.


def test_enum_member_names_equal_values() -> None:
    """SQLAlchemy persists member NAMES; lowercase names keep the DB readable."""
    for enum_cls in (
        ReturnStatus,
        ReturnInitiator,
        ReturnSettlementChoice,
        ReturnReasonCode,
        StoreCreditEntryType,
    ):
        for member in enum_cls:
            assert member.name == member.value, f"{enum_cls.__name__}.{member.name}"


def test_return_status_members() -> None:
    assert {s.value for s in ReturnStatus} == {
        "awaiting_customer_confirmation",
        "active",
        "awaiting_payment_confirmation",
        "closed",
        "rejected",
        "withdrawn",
        "expired",
    }


def test_lock_and_terminal_sets_partition_the_states() -> None:
    from app.models.returns import LINE_LOCKING_STATUSES, TERMINAL_RETURN_STATUSES

    # Every status is either terminal or in-flight; closed is both terminal and
    # line-locking (the goods were returned, so the line can never come back).
    assert TERMINAL_RETURN_STATUSES == {
        ReturnStatus.closed, ReturnStatus.rejected,
        ReturnStatus.withdrawn, ReturnStatus.expired,
    }
    assert LINE_LOCKING_STATUSES == {
        ReturnStatus.awaiting_customer_confirmation, ReturnStatus.active,
        ReturnStatus.awaiting_payment_confirmation, ReturnStatus.closed,
    }
    released = TERMINAL_RETURN_STATUSES - LINE_LOCKING_STATUSES
    assert released == {
        ReturnStatus.rejected, ReturnStatus.withdrawn, ReturnStatus.expired
    }


async def test_return_request_persists_with_defaults(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id,
        customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id,
        seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id,
        initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user.id,
        status=ReturnStatus.awaiting_customer_confirmation,
        is_full_order=True,
        reason_code=ReturnReasonCode.damaged,
        items_amount=100.0,
        delivery_fee_amount=20.0,
        total_amount=120.0,
        settlement_choice=ReturnSettlementChoice.store_credit,
        agreement_policy_version=1,
        window_expires_at=now + timedelta(days=7),
        confirm_expires_at=now + timedelta(hours=48),
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    assert req.id is not None
    assert req.credit_reversal_amount == 0.0
    assert req.store_credit_amount == 0.0
    assert req.payment_amount == 0.0
    assert req.receipt_otp is None
    assert req.receipt_otp_attempts == 0
    assert req.restock is False
    assert req.handover_expires_at is None


async def test_return_request_item_unique_per_order_item(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user.id, status=ReturnStatus.active,
        is_full_order=False, reason_code=ReturnReasonCode.other, reason_note="melted",
        items_amount=50.0, delivery_fee_amount=0.0, total_amount=50.0,
        settlement_choice=ReturnSettlementChoice.payment,
        agreement_policy_version=1, window_expires_at=now, confirm_expires_at=now,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    session.add(ReturnRequestItem(
        return_request_id=req.id, order_item_id=seed.order_item_ids[0], quantity=2,
        product_name_snapshot="Ghee 1L", unit_price_snapshot=25.0, line_total=50.0,
    ))
    await session.commit()

    session.add(ReturnRequestItem(
        return_request_id=req.id, order_item_id=seed.order_item_ids[0], quantity=2,
        product_name_snapshot="Ghee 1L", unit_price_snapshot=25.0, line_total=50.0,
    ))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_return_event_records_transition(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    now = datetime.now(timezone.utc)
    req = ReturnRequest(
        order_id=seed.order_id, customer_profile_id=seed.customer_profile_id,
        store_id=seed.store_id, seller_profile_id=seed.seller_profile_id,
        service_id=seed.service_id, initiated_by=ReturnInitiator.customer,
        initiated_by_user_id=seed.customer_user.id,
        status=ReturnStatus.awaiting_customer_confirmation, is_full_order=False,
        reason_code=ReturnReasonCode.damaged, items_amount=10.0,
        delivery_fee_amount=0.0, total_amount=10.0,
        settlement_choice=ReturnSettlementChoice.payment, agreement_policy_version=1,
        window_expires_at=now, confirm_expires_at=now,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    session.add(ReturnEvent(
        return_request_id=req.id,
        from_status=ReturnStatus.awaiting_customer_confirmation,
        to_status=ReturnStatus.active, actor_role="customer",
        actor_user_id=seed.customer_user.id, note="initiation otp confirmed",
    ))
    await session.commit()
    rows = (await session.exec(select(ReturnEvent))).all()
    assert len(rows) == 1
    assert rows[0].from_status == ReturnStatus.awaiting_customer_confirmation
    assert rows[0].to_status == ReturnStatus.active


async def test_store_credit_account_unique_pair(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    session.add(CustomerStoreCredit(
        seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
    ))
    await session.commit()
    session.add(CustomerStoreCredit(
        seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
    ))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_store_credit_entry_persists(session: AsyncSession) -> None:
    seed = await seed_delivered_order(session)
    acct = CustomerStoreCredit(
        seller_profile_id=seed.seller_profile_id,
        customer_profile_id=seed.customer_profile_id,
    )
    session.add(acct)
    await session.commit()
    await session.refresh(acct)
    assert acct.balance == 0.0
    assert acct.lifetime_earned == 0.0
    assert acct.lifetime_spent == 0.0

    session.add(CustomerStoreCreditEntry(
        account_id=acct.id, entry_type=StoreCreditEntryType.return_credit,
        amount=120.0, balance_after=120.0, note="return #1",
    ))
    await session.commit()
    rows = (await session.exec(select(CustomerStoreCreditEntry))).all()
    assert rows[0].entry_type == StoreCreditEntryType.return_credit


async def test_new_columns_on_existing_tables(session: AsyncSession) -> None:
    from app.models.commerce import Order
    from app.models.profile import SellerProfileService

    assert SellerProfileService(seller_profile_id=1, service_id=1).return_window_days == 0
    assert "store_credit_applied" in Order.model_fields

    seed = await seed_delivered_order(session, return_window_days=5)
    order = await session.get(Order, seed.order_id)
    assert order is not None
    assert order.store_credit_applied == 0.0
