# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.consent import PolicyDocument, PolicyKind
from app.services.consent import get_effective_policy_version


def test_return_agreement_is_a_policy_kind() -> None:
    assert PolicyKind.return_agreement.value == "return_agreement"
    # Member NAME must equal the value: SQLAlchemy persists names.
    assert PolicyKind.return_agreement.name == "return_agreement"


async def test_admin_can_publish_return_agreement(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/admin/policies/return_agreement",
        json={"body": "Returned goods must be unused and in original packaging."},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["kind"] == "return_agreement"
    assert resp.json()["version"] == 1


async def test_public_get_returns_published_agreement(
    client: AsyncClient, admin_auth_headers: dict[str, str]
) -> None:
    await client.post(
        "/api/v1/admin/policies/return_agreement",
        json={"body": "v1 terms"},
        headers=admin_auth_headers,
    )
    resp = await client.get("/api/v1/policies/return_agreement")
    assert resp.status_code == 200
    assert resp.json()["body"] == "v1 terms"


async def test_unpublished_agreement_is_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/policies/return_agreement")
    assert resp.status_code == 404


async def test_agreement_does_not_affect_consent_gate(session: AsyncSession) -> None:
    """The effective consent version reads terms + privacy only. Publishing a
    return agreement must never force every user to re-accept."""
    session.add(PolicyDocument(kind=PolicyKind.terms, version=1, body="t"))
    session.add(PolicyDocument(kind=PolicyKind.privacy, version=1, body="p"))
    await session.commit()
    before = await get_effective_policy_version(session)

    session.add(PolicyDocument(kind=PolicyKind.return_agreement, version=1, body="r"))
    await session.commit()
    after = await get_effective_policy_version(session)

    assert before == "t1-p1"
    assert after == before
