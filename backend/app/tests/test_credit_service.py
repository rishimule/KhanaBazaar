# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from fastapi import HTTPException

from app.models.credit import CreditAccountStatus, CreditEntryType
from app.services import credit as svc
from tests._credit_helpers import enable_credit, make_customer


async def _seller_and_customer(session, approved_seller, *, cap=5000.0):
    seller_id = approved_seller["profile"].id
    await enable_credit(session, seller_id, max_limit_per_customer=cap)
    cust = await make_customer(session, phone="+919812345678")
    return seller_id, cust


@pytest.mark.asyncio
async def test_grant_requires_enabled(session, approved_seller):
    seller_id = approved_seller["profile"].id  # no config row → disabled
    cust = await make_customer(session)
    with pytest.raises(HTTPException) as exc:
        await svc.grant_credit(session, seller_profile_id=seller_id,
                               granted_by_user_id=cust["user"].id,
                               customer_profile_id=cust["profile"].id, credit_limit=100)
    assert exc.value.detail["error"] == "credit_not_enabled"


@pytest.mark.asyncio
async def test_grant_rejects_over_cap_and_nonpositive(session, approved_seller):
    seller_id, cust = await _seller_and_customer(session, approved_seller, cap=1000)
    with pytest.raises(HTTPException) as exc:
        await svc.grant_credit(session, seller_profile_id=seller_id,
                               granted_by_user_id=cust["user"].id,
                               customer_profile_id=cust["profile"].id, credit_limit=2000)
    assert exc.value.detail["error"] == "limit_exceeds_cap"
    with pytest.raises(HTTPException) as exc2:
        await svc.grant_credit(session, seller_profile_id=seller_id,
                               granted_by_user_id=cust["user"].id,
                               customer_profile_id=cust["profile"].id, credit_limit=0)
    assert exc2.value.detail["error"] == "invalid_limit"


@pytest.mark.asyncio
async def test_grant_then_duplicate_and_resolve(session, approved_seller):
    seller_id, cust = await _seller_and_customer(session, approved_seller)
    acct = await svc.grant_credit(session, seller_profile_id=seller_id,
                                  granted_by_user_id=cust["user"].id,
                                  customer_profile_id=cust["profile"].id, credit_limit=2000)
    assert acct.status == CreditAccountStatus.active
    with pytest.raises(HTTPException) as exc:
        await svc.grant_credit(session, seller_profile_id=seller_id,
                               granted_by_user_id=cust["user"].id,
                               customer_profile_id=cust["profile"].id, credit_limit=500)
    assert exc.value.detail["error"] == "account_exists"
    # resolve by phone + by email
    by_phone = await svc.resolve_customer(session, phone="+919812345678")
    assert by_phone.id == cust["profile"].id
    by_email = await svc.resolve_customer(session, email=cust["user"].email)
    assert by_email.id == cust["profile"].id
    with pytest.raises(HTTPException) as exc2:
        await svc.resolve_customer(session, phone="+910000000000")
    assert exc2.value.detail["error"] == "invalid_phone"


@pytest.mark.asyncio
async def test_adjust_below_outstanding_blocked(session, approved_seller):
    seller_id, cust = await _seller_and_customer(session, approved_seller)
    acct = await svc.grant_credit(session, seller_profile_id=seller_id,
                                  granted_by_user_id=cust["user"].id,
                                  customer_profile_id=cust["profile"].id, credit_limit=2000)
    acct.outstanding_balance = 800.0
    session.add(acct)
    await session.commit()
    await session.refresh(acct)
    with pytest.raises(HTTPException) as exc:
        await svc.adjust_credit_account(session, account=acct, credit_limit=500)
    assert exc.value.detail["error"] == "below_outstanding"
    # suspend works
    updated = await svc.adjust_credit_account(session, account=acct,
                                              status=CreditAccountStatus.suspended)
    assert updated.status == CreditAccountStatus.suspended


@pytest.mark.asyncio
async def test_repayment_math_and_over_repayment(session, approved_seller):
    seller_id, cust = await _seller_and_customer(session, approved_seller)
    acct = await svc.grant_credit(session, seller_profile_id=seller_id,
                                  granted_by_user_id=cust["user"].id,
                                  customer_profile_id=cust["profile"].id, credit_limit=2000)
    acct.outstanding_balance = 1000.0
    session.add(acct)
    await session.commit()
    await session.refresh(acct)
    with pytest.raises(HTTPException) as exc:
        await svc.record_repayment(session, account=acct, amount=1500, note=None,
                                   recorded_by_user_id=cust["user"].id)
    assert exc.value.detail["error"] == "over_repayment"
    entry = await svc.record_repayment(session, account=acct, amount=400, note="cash",
                                       recorded_by_user_id=cust["user"].id)
    assert entry.entry_type == CreditEntryType.repayment
    assert entry.balance_after == 600.0
    await session.refresh(acct)
    assert acct.outstanding_balance == 600.0


@pytest.mark.asyncio
async def test_repayment_reads_fresh_locked_state(session, approved_seller):
    """record_repayment must refresh under lock so a stale in-memory
    outstanding_balance can't erase a concurrently-committed charge."""
    seller_id, cust = await _seller_and_customer(session, approved_seller)
    acct = await svc.grant_credit(session, seller_profile_id=seller_id,
                                  granted_by_user_id=cust["user"].id,
                                  customer_profile_id=cust["profile"].id, credit_limit=2000)
    acct.outstanding_balance = 1000.0
    session.add(acct)
    await session.commit()
    await session.refresh(acct)
    # Make the in-memory copy stale (DB still says 1000).
    acct.outstanding_balance = 0.0
    entry = await svc.record_repayment(session, account=acct, amount=400, note=None,
                                       recorded_by_user_id=cust["user"].id)
    # With the FOR-UPDATE refresh, the true 1000 is used → 600, not a bogus value.
    assert entry.balance_after == 600.0


@pytest.mark.asyncio
async def test_grandfather_on_tighten(session, approved_seller):
    seller_id = approved_seller["profile"].id
    cfg = await enable_credit(session, seller_id, max_limit_per_customer=5000)
    cust = await make_customer(session, phone="+919812345678")
    acct = await svc.grant_credit(session, seller_profile_id=seller_id,
                                  granted_by_user_id=cust["user"].id,
                                  customer_profile_id=cust["profile"].id, credit_limit=5000)
    acct.outstanding_balance = 800.0
    session.add(acct)
    await session.commit()

    # Admin lowers the cap.
    cfg.max_limit_per_customer = 1000
    session.add(cfg)
    await session.commit()

    # Existing account limit is grandfathered (unchanged).
    await session.refresh(acct)
    assert acct.credit_limit == 5000

    # A NEW grant is capped at the lowered value.
    cust2 = await make_customer(session)
    with pytest.raises(HTTPException) as exc:
        await svc.grant_credit(session, seller_profile_id=seller_id,
                               granted_by_user_id=cust2["user"].id,
                               customer_profile_id=cust2["profile"].id, credit_limit=2000)
    assert exc.value.detail["error"] == "limit_exceeds_cap"

    # Repayment on the grandfathered account still works.
    entry = await svc.record_repayment(session, account=acct, amount=300, note=None,
                                       recorded_by_user_id=cust["user"].id)
    assert entry.balance_after == 500.0
