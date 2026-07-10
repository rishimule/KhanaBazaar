# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select

from app.models.commerce import PaymentMethod
from app.models.credit import (
    CreditAccount,
    CreditAccountStatus,
    CreditEntryType,
    CreditLedgerEntry,
    SellerCreditConfig,
)
from app.models.notification import NotificationType
from tests._credit_helpers import make_customer


@pytest.mark.asyncio
async def test_credit_rows_roundtrip(session, approved_seller):
    seller_id = approved_seller["profile"].id
    customer = await make_customer(session)

    cfg = SellerCreditConfig(
        seller_profile_id=seller_id, credit_enabled=True, max_limit_per_customer=5000
    )
    session.add(cfg)
    acct = CreditAccount(
        seller_profile_id=seller_id,
        customer_profile_id=customer["profile"].id,
        credit_limit=2000,
        granted_by_user_id=customer["user"].id,
    )
    session.add(acct)
    await session.commit()
    await session.refresh(acct)
    assert acct.outstanding_balance == 0.0
    assert acct.status == CreditAccountStatus.active
    assert acct.last_notified_threshold == 0

    entry = CreditLedgerEntry(
        credit_account_id=acct.id,
        entry_type=CreditEntryType.charge,
        amount=500,
        balance_after=500,
    )
    session.add(entry)
    await session.commit()
    got = (
        await session.exec(
            select(CreditLedgerEntry).where(
                CreditLedgerEntry.credit_account_id == acct.id
            )
        )
    ).one()
    assert got.entry_type == CreditEntryType.charge
    assert got.order_id is None


def test_new_enum_values():
    assert PaymentMethod.Credit.value == "credit"
    assert NotificationType.Credit.value == "credit"
