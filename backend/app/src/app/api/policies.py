# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Policy endpoints.

`router`        — public reads + consent status, mounted at /api/v1/policies.
`admin_router`  — admin publish/list/history, mounted at /api/v1/admin.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import get_db_session
from app.models.consent import PolicyDocument, PolicyKind
from app.schemas.policies import PolicyDocumentRead, PolicyStatusRead
from app.services.consent import get_effective_policy_version

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
