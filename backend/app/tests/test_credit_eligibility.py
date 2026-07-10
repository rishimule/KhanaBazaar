# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import contextlib

import pytest

from app import app
from app.core.security import get_current_customer, get_current_user
from app.models.credit import CreditAccount, CreditAccountStatus
from tests._credit_helpers import enable_credit, make_customer


@contextlib.contextmanager
def as_customer(user):
    app.dependency_overrides[get_current_customer] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_customer, None)
        app.dependency_overrides.pop(get_current_user, None)


async def _account(session, bundle, cust, *, limit=2000.0, outstanding=0.0,
                   status=CreditAccountStatus.active, enabled=True):
    await enable_credit(session, bundle.profile.id) if enabled else None
    acct = CreditAccount(seller_profile_id=bundle.profile.id, customer_profile_id=cust["profile"].id,
                         credit_limit=limit, outstanding_balance=outstanding, status=status,
                         granted_by_user_id=bundle.user_id)
    session.add(acct)
    await session.commit()


@pytest.mark.asyncio
async def test_eligible_when_available_covers_total(client, session, approved_seller_with_store):
    b = approved_seller_with_store
    cust = await make_customer(session)
    await _account(session, b, cust, limit=2000, outstanding=500)  # available 1500
    with as_customer(cust["user"]):
        r = await client.get(f"/api/v1/customers/me/credit/eligibility?store_id={b.store.id}&total=1000")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"eligible": True, "available": 1500.0, "credit_limit": 2000.0,
                    "outstanding_balance": 500.0}


@pytest.mark.asyncio
async def test_ineligible_when_total_exceeds_available(client, session, approved_seller_with_store):
    b = approved_seller_with_store
    cust = await make_customer(session)
    await _account(session, b, cust, limit=1000, outstanding=800)  # available 200
    with as_customer(cust["user"]):
        r = await client.get(f"/api/v1/customers/me/credit/eligibility?store_id={b.store.id}&total=500")
    assert r.json()["eligible"] is False


@pytest.mark.asyncio
async def test_ineligible_when_no_account(client, session, approved_seller_with_store):
    b = approved_seller_with_store
    cust = await make_customer(session)
    with as_customer(cust["user"]):
        r = await client.get(f"/api/v1/customers/me/credit/eligibility?store_id={b.store.id}&total=1")
    assert r.status_code == 200
    assert r.json() == {"eligible": False, "available": 0.0, "credit_limit": 0.0,
                        "outstanding_balance": 0.0}
