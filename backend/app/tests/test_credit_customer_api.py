# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import contextlib

import pytest

from app import app
from app.core.security import get_current_customer, get_current_user
from app.models.credit import CreditAccount
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


@pytest.mark.asyncio
async def test_customer_sees_their_credit(client, session, approved_seller_with_store):
    bundle = approved_seller_with_store
    spid = bundle.profile.id
    await enable_credit(session, spid, max_limit_per_customer=5000)
    cust = await make_customer(session)
    acct = CreditAccount(seller_profile_id=spid, customer_profile_id=cust["profile"].id,
                         credit_limit=2000, outstanding_balance=750,
                         granted_by_user_id=bundle.user_id)
    session.add(acct)
    await session.commit()

    with as_customer(cust["user"]):
        r = await client.get("/api/v1/customers/me/credit")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["store_name"] == bundle.store.name
    assert body[0]["available"] == 1250.0
    assert body[0]["outstanding_balance"] == 750.0


@pytest.mark.asyncio
async def test_customer_with_no_credit_sees_empty(client, session):
    cust = await make_customer(session)
    with as_customer(cust["user"]):
        r = await client.get("/api/v1/customers/me/credit")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_credit_view_rejects_non_customer(client):
    from app.core.security import get_current_customer as gcc
    from fastapi import HTTPException

    async def _deny() -> None:
        raise HTTPException(status_code=403, detail="Customer role required")

    app.dependency_overrides[gcc] = _deny
    try:
        r = await client.get("/api/v1/customers/me/credit")
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(gcc, None)
