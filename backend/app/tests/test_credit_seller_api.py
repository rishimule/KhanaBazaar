# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import contextlib

import pytest

from app import app
from app.core.security import get_current_seller, get_current_user
from app.models.credit import CreditAccount
from tests._credit_helpers import enable_credit, make_customer


@contextlib.contextmanager
def as_seller(user):
    app.dependency_overrides[get_current_seller] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_seller_grant_list_repay_ledger(client, session, approved_seller):
    spid = approved_seller["profile"].id
    await enable_credit(session, spid, max_limit_per_customer=5000)
    cust = await make_customer(session, phone="+919812345678")

    with as_seller(approved_seller["user"]):
        r = await client.post("/api/v1/credit/accounts",
                              json={"customer_phone": "+919812345678", "credit_limit": 2000})
        assert r.status_code == 201, r.text
        acct_id = r.json()["id"]
        assert r.json()["available"] == 2000.0

        r = await client.get("/api/v1/credit/accounts")
        assert r.status_code == 200 and any(a["id"] == acct_id for a in r.json())

        # bump outstanding to allow a repayment (charge lands in Task 7)
        acct = await session.get(CreditAccount, acct_id)
        acct.outstanding_balance = 900.0
        session.add(acct)
        await session.commit()

        r = await client.post(f"/api/v1/credit/accounts/{acct_id}/repayments",
                              json={"amount": 300, "note": "cash"})
        assert r.status_code == 200, r.text
        assert r.json()["balance_after"] == 600.0

        r = await client.get(f"/api/v1/credit/accounts/{acct_id}/ledger")
        assert r.status_code == 200 and r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_seller_cannot_touch_others_account(client, session, approved_seller):
    # seller A owns an account
    spid_a = approved_seller["profile"].id
    await enable_credit(session, spid_a)
    cust = await make_customer(session, phone="+919812345678")
    with as_seller(approved_seller["user"]):
        r = await client.post("/api/v1/credit/accounts",
                              json={"customer_phone": "+919812345678", "credit_limit": 1000})
        acct_id = r.json()["id"]

    # seller B tries to read/patch it
    from tests.conftest import _make_seller
    from app.models.profile import VerificationStatus
    seller_b = await _make_seller(session, status=VerificationStatus.Approved)
    with as_seller(seller_b["user"]):
        r = await client.get(f"/api/v1/credit/accounts/{acct_id}/ledger")
        assert r.status_code == 404
        r = await client.patch(f"/api/v1/credit/accounts/{acct_id}",
                              json={"status": "suspended"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_seller_routes_reject_customer(client, customer_auth_headers):
    r = await client.get("/api/v1/credit/accounts", headers=customer_auth_headers)
    assert r.status_code == 403
