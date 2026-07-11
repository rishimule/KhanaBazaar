# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select

from app.models.commerce import PaymentMethod
from app.models.credit import CreditAccount
from app.models.notification import Notification, NotificationType
from app.services.checkout import place_order_for_sub_basket
from app.services.credit_notifications import (
    notify_credit_granted,
    record_and_dispatch_credit_charge_notifications,
)
from tests._credit_helpers import make_customer
from tests.test_credit_checkout import _seed


async def _credit_notifs(session, *, status_value):
    rows = (
        await session.exec(
            select(Notification).where(
                Notification.type == NotificationType.Credit,
                Notification.status_value == status_value,
            )
        )
    ).all()
    return list(rows)


@pytest.mark.asyncio
async def test_grant_notifies_customer(session, approved_seller_with_store):
    b = approved_seller_with_store
    cust = await make_customer(session)
    acct = CreditAccount(seller_profile_id=b.profile.id, customer_profile_id=cust["profile"].id,
                         credit_limit=2000, granted_by_user_id=b.user_id)
    session.add(acct)
    await session.commit()
    await notify_credit_granted(session, acct)
    granted = await _credit_notifs(session, status_value="granted")
    assert len(granted) == 1
    assert granted[0].customer_profile_id == cust["profile"].id


@pytest.mark.asyncio
async def test_threshold_fires_once_and_balance_each_time(session):
    # limit 125, order total 100 -> 80% usage
    s = await _seed(session, credit_limit=125.0)
    order = await place_order_for_sub_basket(
        session, s["user"], customer_address_id=s["address_id"], store_id=s["store_id"], service_id=s["service_id"], payment_method=PaymentMethod.Credit
    )
    await record_and_dispatch_credit_charge_notifications(session, order)

    threshold = await _credit_notifs(session, status_value="threshold")
    assert len(threshold) == 2  # seller + customer, once
    balance = await _credit_notifs(session, status_value="balance")
    assert len(balance) == 1

    # A second dispatch with no new charge (still 80%) must NOT re-fire threshold,
    # but does add another balance notification.
    await record_and_dispatch_credit_charge_notifications(session, order)
    assert len(await _credit_notifs(session, status_value="threshold")) == 2
    assert len(await _credit_notifs(session, status_value="balance")) == 2

    acct = (await session.exec(select(CreditAccount).where(
        CreditAccount.seller_profile_id == s["seller_profile_id"]))).one()
    assert acct.last_notified_threshold == 80
