# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""The return agreement must be seeded on deploy and listable by an admin.

Without both, returns are dead on arrival in production: `create_return`
refuses with `agreement_unavailable` and the admin dashboard offers no card to
publish one, because `seed_database.py --skip-if-seeded` skips the dev seed on a
populated catalog.
"""
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.seed_policies import seed_policies
from app.models.consent import PolicyDocument, PolicyKind
from app.services.consent import get_current_version


async def test_seed_policies_publishes_the_return_agreement(
    session: AsyncSession,
) -> None:
    created = await seed_policies(session)
    assert created[PolicyKind.return_agreement.value] == 1

    version = await get_current_version(session, PolicyKind.return_agreement)
    assert version == 1
    doc = (
        await session.exec(
            select(PolicyDocument).where(
                PolicyDocument.kind == PolicyKind.return_agreement
            )
        )
    ).first()
    assert doc is not None
    assert "Part of an item cannot be returned" in doc.body


async def test_seed_policies_is_idempotent(session: AsyncSession) -> None:
    first = await seed_policies(session)
    assert first[PolicyKind.return_agreement.value] == 1
    second = await seed_policies(session)
    assert second[PolicyKind.return_agreement.value] == 0

    rows = (
        await session.exec(
            select(PolicyDocument).where(
                PolicyDocument.kind == PolicyKind.return_agreement
            )
        )
    ).all()
    assert len(rows) == 1


async def test_admin_policy_list_includes_the_return_agreement(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/admin/policies", headers=admin_auth_headers)
    assert resp.status_code == 200, resp.text
    kinds = [item["kind"] for item in resp.json()]
    assert "return_agreement" in kinds
    # Every PolicyKind must be listed, so a future kind cannot be stranded
    # without a way to publish it.
    assert set(kinds) == {k.value for k in PolicyKind}


async def test_admin_can_publish_an_unseeded_kind(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    """An admin revising the agreement bumps the version."""
    first = await client.post(
        "/api/v1/admin/policies/return_agreement",
        json={"body": "v1 terms"}, headers=admin_auth_headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1

    second = await client.post(
        "/api/v1/admin/policies/return_agreement",
        json={"body": "v2 terms"}, headers=admin_auth_headers,
    )
    assert second.json()["version"] == 2
