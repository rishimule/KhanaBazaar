# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import app.services.account_lifecycle as lifecycle
from app.models.base import AccountStatus, User, UserRole
from app.models.customer_account_event import CustomerAccountEvent
from app.models.profile import CustomerProfile
from app.services.account_lifecycle import (
    InvalidTransition,
    OpenObligations,
    has_open_obligations,
    transition,
)


async def _seed_customer(
    session: AsyncSession, email: str
) -> tuple[User, CustomerProfile]:
    user = User(email=email, role=UserRole.Customer)
    session.add(user)
    await session.flush()
    assert user.id is not None
    profile = CustomerProfile(user_id=user.id, first_name="Test")
    session.add(profile)
    await session.commit()
    await session.refresh(user)
    await session.refresh(profile)
    return user, profile


async def _seed_admin(session: AsyncSession, email: str) -> int:
    admin = User(email=email, role=UserRole.Admin)
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    assert admin.id is not None
    return admin.id


@pytest.mark.asyncio
async def test_deactivate_from_active(session: AsyncSession) -> None:
    user, _ = await _seed_customer(session, "svc-deac@kb.com")
    assert user.id is not None
    updated = await transition(
        session, user_id=user.id, to_status=AccountStatus.deactivated,
        actor_user_id=None, actor_role="customer", reason="bye",
        enforce_obligations=True,
    )
    await session.commit()
    assert updated.account_status == AccountStatus.deactivated
    assert updated.is_active is False
    assert updated.status_changed_at is not None
    ev = (await session.exec(select(CustomerAccountEvent))).all()
    assert len(ev) == 1
    assert ev[0].from_status == AccountStatus.active
    assert ev[0].to_status == AccountStatus.deactivated
    assert ev[0].actor_role == "customer"


@pytest.mark.asyncio
async def test_illegal_transition_raises(session: AsyncSession) -> None:
    user, _ = await _seed_customer(session, "svc-illegal@kb.com")
    assert user.id is not None
    # active -> active is not a legal transition.
    with pytest.raises(InvalidTransition):
        await transition(
            session, user_id=user.id, to_status=AccountStatus.active,
            actor_user_id=None, actor_role="customer", reason=None,
            enforce_obligations=False,
        )


@pytest.mark.asyncio
async def test_has_open_obligations_zero_for_clean_customer(
    session: AsyncSession,
) -> None:
    _, profile = await _seed_customer(session, "svc-clean@kb.com")
    assert profile.id is not None
    orders, credits = await has_open_obligations(session, profile.id)
    assert orders == 0
    assert credits == 0


@pytest.mark.asyncio
async def test_open_obligations_blocks_self_delete(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _ = await _seed_customer(session, "svc-openobl@kb.com")
    assert user.id is not None

    async def _fake(_session: AsyncSession, _cid: int) -> tuple[int, int]:
        return (1, 0)

    monkeypatch.setattr(lifecycle, "has_open_obligations", _fake)
    with pytest.raises(OpenObligations) as exc:
        await transition(
            session, user_id=user.id, to_status=AccountStatus.deleted,
            actor_user_id=None, actor_role="customer", reason=None,
            enforce_obligations=True,
        )
    assert exc.value.open_orders == 1


@pytest.mark.asyncio
async def test_admin_delete_bypasses_obligation_guard(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _ = await _seed_customer(session, "svc-adminoverride@kb.com")
    admin_id = await _seed_admin(session, "svc-admin1@kb.com")
    assert user.id is not None

    async def _fake(_session: AsyncSession, _cid: int) -> tuple[int, int]:
        return (5, 2)  # obligations exist, but admin bypasses the guard

    monkeypatch.setattr(lifecycle, "has_open_obligations", _fake)
    updated = await transition(
        session, user_id=user.id, to_status=AccountStatus.deleted,
        actor_user_id=admin_id, actor_role="admin", reason="fraud detected",
        enforce_obligations=False,
    )
    await session.commit()
    assert updated.account_status == AccountStatus.deleted
    assert updated.status_changed_by_user_id == admin_id


@pytest.mark.asyncio
async def test_deleted_restores_to_active_only(session: AsyncSession) -> None:
    user, _ = await _seed_customer(session, "svc-restore@kb.com")
    admin_id = await _seed_admin(session, "svc-admin2@kb.com")
    assert user.id is not None
    await transition(
        session, user_id=user.id, to_status=AccountStatus.deleted,
        actor_user_id=admin_id, actor_role="admin", reason="removed",
        enforce_obligations=False,
    )
    await session.commit()
    # deleted -> active is legal (admin restore)
    updated = await transition(
        session, user_id=user.id, to_status=AccountStatus.active,
        actor_user_id=admin_id, actor_role="admin", reason="appeal granted",
        enforce_obligations=False,
    )
    await session.commit()
    assert updated.account_status == AccountStatus.active
    assert updated.is_active is True
