# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Guards for the returns dev seeder.

The seeder is what QA and the frontend work against, so a silent break there
costs real time. These run against the test DB, not the dev one.
"""
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.dev_seed import _seed_returns
from app.models.consent import PolicyDocument, PolicyKind
from app.models.profile import SellerProfileService
from app.models.returns import CustomerStoreCredit, ReturnRequest, ReturnStatus
from tests._returns_helpers import seed_delivered_order


async def test_seeder_is_a_noop_without_delivered_orders(
    session: AsyncSession,
) -> None:
    await _seed_returns(session)
    await session.commit()
    assert (await session.exec(select(func.count()).select_from(ReturnRequest))).one() == 0


async def test_seeder_publishes_the_agreement_and_sets_windows(
    session: AsyncSession,
) -> None:
    await seed_delivered_order(session, return_window_days=0)
    await _seed_returns(session)
    await session.commit()

    agreement = (
        await session.exec(
            select(PolicyDocument).where(
                PolicyDocument.kind == PolicyKind.return_agreement
            )
        )
    ).first()
    assert agreement is not None
    assert "handover code" in agreement.body

    # An unknown service slug falls back to the 7-day default rather than 0,
    # so seeded stores are returnable out of the box.
    row = (await session.exec(select(SellerProfileService))).first()
    assert row is not None
    assert row.return_window_days == 7


async def test_seeder_builds_returns_and_is_idempotent(
    session: AsyncSession,
) -> None:
    for i in range(7):
        await seed_delivered_order(session, email_suffix=f"seed{i}")

    await _seed_returns(session)
    await session.commit()
    first_pass = (
        await session.exec(select(func.count()).select_from(ReturnRequest))
    ).one()
    assert first_pass == 7

    states = {
        r.status
        for r in (await session.exec(select(ReturnRequest))).all()
    }
    assert states == set(ReturnStatus), "every resting state should have an example"

    # The closed return grants store credit so the account page has history.
    credit = (await session.exec(select(CustomerStoreCredit))).all()
    assert len(credit) == 1
    assert credit[0].balance > 0

    await _seed_returns(session)
    await session.commit()
    assert (
        await session.exec(select(func.count()).select_from(ReturnRequest))
    ).one() == first_pass
