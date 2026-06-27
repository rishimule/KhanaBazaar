# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.base import User, UserRole
from app.models.consent import PolicyAcceptance, PolicyDocument, PolicyKind


@pytest.mark.asyncio
async def test_policy_document_unique_kind_version(session: AsyncSession) -> None:
    session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="v1", published_by=None))
    await session.commit()
    session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="dup", published_by=None))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_policy_acceptance_unique_user_version(session: AsyncSession) -> None:
    user = User(email="c1@kb.test", role=UserRole.Customer)
    session.add(user)
    await session.flush()
    assert user.id is not None
    session.add(PolicyAcceptance(user_id=user.id, policy_version="t1-p1"))
    await session.commit()
    session.add(PolicyAcceptance(user_id=user.id, policy_version="t1-p1"))
    with pytest.raises(IntegrityError):
        await session.commit()
