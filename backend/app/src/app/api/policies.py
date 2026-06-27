# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Policy endpoints.

`router`        — public reads + consent status, mounted at /api/v1/policies.
`admin_router`  — admin publish/list/history, mounted at /api/v1/admin.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin
from app.db.session import get_db_session
from app.models.base import User
from app.models.consent import PolicyDocument, PolicyKind
from app.schemas.policies import (
    PolicyAdminItem,
    PolicyDocumentRead,
    PolicyHistoryItem,
    PolicyPublishBody,
    PolicyStatusRead,
)
from app.services.consent import get_current_version, get_effective_policy_version

router = APIRouter()
admin_router = APIRouter()


async def _current_document(
    session: AsyncSession, kind: PolicyKind
) -> PolicyDocument | None:
    result = await session.exec(
        select(PolicyDocument)
        .where(PolicyDocument.kind == kind)
        .order_by(PolicyDocument.version.desc())  # type: ignore[attr-defined]
        .limit(1)
    )
    return result.first()


@router.get("/status", response_model=PolicyStatusRead)
async def policy_status(
    session: AsyncSession = Depends(get_db_session),
) -> PolicyStatusRead:
    version = await get_effective_policy_version(session)
    return PolicyStatusRead(required=version is not None, version=version)


@router.get("/{kind}", response_model=PolicyDocumentRead)
async def get_policy(
    kind: PolicyKind,
    session: AsyncSession = Depends(get_db_session),
) -> PolicyDocumentRead:
    doc = await _current_document(session, kind)
    if doc is None:
        raise HTTPException(status_code=404, detail={"error": "policy_not_published"})
    return PolicyDocumentRead(
        kind=doc.kind.value,
        version=doc.version,
        body=doc.body,
        published_at=doc.created_at,
    )


@admin_router.get("/policies", response_model=list[PolicyAdminItem])
async def admin_list_policies(
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[PolicyAdminItem]:
    items: list[PolicyAdminItem] = []
    for kind in (PolicyKind.terms, PolicyKind.privacy):
        doc = await _current_document(session, kind)
        if doc is None:
            items.append(
                PolicyAdminItem(kind=kind.value, version=0, body="", published_at=None)
            )
        else:
            items.append(
                PolicyAdminItem(
                    kind=kind.value,
                    version=doc.version,
                    body=doc.body,
                    published_at=doc.created_at,
                )
            )
    return items


@admin_router.post("/policies/{kind}", response_model=PolicyDocumentRead)
async def admin_publish_policy(
    kind: PolicyKind,
    body: PolicyPublishBody,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> PolicyDocumentRead:
    # Retry on the (kind, version) unique-constraint race: a concurrent publish
    # of the same kind commits version N+1 first, so recompute and retry rather
    # than 500.
    for _ in range(3):
        next_version = await get_current_version(session, kind) + 1
        doc = PolicyDocument(
            kind=kind, version=next_version, body=body.body, published_by=admin.id
        )
        session.add(doc)
        try:
            await session.commit()
            break
        except IntegrityError:
            await session.rollback()
    else:
        raise HTTPException(status_code=409, detail={"error": "version_conflict"})
    await session.refresh(doc)
    return PolicyDocumentRead(
        kind=doc.kind.value,
        version=doc.version,
        body=doc.body,
        published_at=doc.created_at,
    )


@admin_router.get("/policies/{kind}/history", response_model=list[PolicyHistoryItem])
async def admin_policy_history(
    kind: PolicyKind,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[PolicyHistoryItem]:
    result = await session.exec(
        select(PolicyDocument)
        .where(PolicyDocument.kind == kind)
        .order_by(PolicyDocument.version.desc())  # type: ignore[attr-defined]
    )
    return [
        PolicyHistoryItem(
            version=d.version, published_at=d.created_at, published_by=d.published_by
        )
        for d in result.all()
    ]
