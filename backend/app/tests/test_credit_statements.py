# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select

from app.models.credit import CreditAccount, CreditAccountStatus
from app.models.notification import Notification, NotificationType
from app.services.credit_notifications import run_credit_statements
from tests._credit_helpers import make_customer


@pytest.mark.asyncio
async def test_monthly_statements_skip_zero_balance(session, approved_seller_with_store):
    b = approved_seller_with_store
    c1 = await make_customer(session)
    c2 = await make_customer(session)
    c3 = await make_customer(session)
    session.add_all([
        CreditAccount(seller_profile_id=b.profile.id, customer_profile_id=c1["profile"].id,
                      credit_limit=2000, outstanding_balance=500, granted_by_user_id=b.user_id),
        CreditAccount(seller_profile_id=b.profile.id, customer_profile_id=c2["profile"].id,
                      credit_limit=2000, outstanding_balance=1200, granted_by_user_id=b.user_id),
        # zero balance -> skipped
        CreditAccount(seller_profile_id=b.profile.id, customer_profile_id=c3["profile"].id,
                      credit_limit=2000, outstanding_balance=0, granted_by_user_id=b.user_id),
    ])
    await session.commit()

    count = await run_credit_statements(session)
    assert count == 2

    stmts = (await session.exec(select(Notification).where(
        Notification.type == NotificationType.Credit,
        Notification.status_value == "statement"))).all()
    # 2 accounts x (seller + customer) = 4
    assert len(stmts) == 4
    assert sum(1 for n in stmts if n.seller_profile_id is not None) == 2
    assert sum(1 for n in stmts if n.customer_profile_id is not None) == 2


@pytest.mark.asyncio
async def test_monthly_statements_skip_suspended(session, approved_seller_with_store):
    b = approved_seller_with_store
    c1 = await make_customer(session)
    session.add(
        CreditAccount(seller_profile_id=b.profile.id, customer_profile_id=c1["profile"].id,
                      credit_limit=2000, outstanding_balance=500,
                      status=CreditAccountStatus.suspended, granted_by_user_id=b.user_id)
    )
    await session.commit()
    assert await run_credit_statements(session) == 0
