# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Policy-consent helpers: effective version + acceptance recording.

The "effective version" is a single token combining the current published
versions of both policy kinds, e.g. "t2-p1". It is None (consent dormant)
until BOTH kinds have a published document. The policy_document table is
tiny (~2 rows), so these are computed directly with no caching.
"""
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.consent import PolicyAcceptance, PolicyDocument, PolicyKind


async def get_current_version(session: AsyncSession, kind: PolicyKind) -> int:
    result = await session.exec(
        select(func.max(PolicyDocument.version)).where(PolicyDocument.kind == kind)
    )
    return int(result.one() or 0)


async def get_effective_policy_version(session: AsyncSession) -> str | None:
    terms_v = await get_current_version(session, PolicyKind.terms)
    privacy_v = await get_current_version(session, PolicyKind.privacy)
    if terms_v == 0 or privacy_v == 0:
        return None
    return f"t{terms_v}-p{privacy_v}"


async def has_accepted_current_policy(session: AsyncSession, user_id: int) -> bool:
    version = await get_effective_policy_version(session)
    if version is None:
        return True
    result = await session.exec(
        select(PolicyAcceptance.id).where(
            PolicyAcceptance.user_id == user_id,
            PolicyAcceptance.policy_version == version,
        )
    )
    return result.first() is not None


async def record_acceptance(session: AsyncSession, user_id: int) -> str | None:
    """Idempotently record acceptance of the current effective version.

    Flushes only — the caller owns the commit so signup can record acceptance
    in the same transaction as account creation. Returns the version recorded
    (or already present), or None when consent is not required.
    """
    version = await get_effective_policy_version(session)
    if version is None:
        return None
    existing = await session.exec(
        select(PolicyAcceptance.id).where(
            PolicyAcceptance.user_id == user_id,
            PolicyAcceptance.policy_version == version,
        )
    )
    if existing.first() is not None:
        return version
    # Savepoint so a concurrent identical insert (gate double-fire / retry)
    # losing the (user_id, policy_version) unique-constraint race is swallowed
    # without poisoning the caller's outer transaction.
    try:
        async with session.begin_nested():
            session.add(PolicyAcceptance(user_id=user_id, policy_version=version))
    except IntegrityError:
        pass
    return version
