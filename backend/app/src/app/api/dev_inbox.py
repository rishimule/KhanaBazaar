# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Development-only inbox for captured outbound emails/SMS (dev_email/dev_sms).

Gated to ENVIRONMENT == "development" (404 otherwise) and protected by HTTP
Basic auth from DEV_INBOX_USER / DEV_INBOX_PASSWORD. Read-only.
"""
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.db.session import get_db_session
from app.models.dev_email import DevEmail
from app.models.dev_sms import DevSms
from app.models.dev_whatsapp import DevWhatsApp

router = APIRouter()
_basic = HTTPBasic(auto_error=False)


def require_dev_inbox(
    credentials: HTTPBasicCredentials | None = Depends(_basic),
) -> None:
    # Read settings live so tests can monkeypatch ENVIRONMENT / creds.
    if settings.ENVIRONMENT != "development":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not settings.DEV_INBOX_USER or not settings.DEV_INBOX_PASSWORD:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    # Compare as bytes: compare_digest rejects non-ASCII str (→ TypeError/500),
    # so encode both sides. Both checks run unconditionally (no short-circuit)
    # to avoid leaking which field was wrong.
    ok_user = secrets.compare_digest(
        credentials.username.encode("utf-8"), settings.DEV_INBOX_USER.encode("utf-8")
    )
    ok_pass = secrets.compare_digest(
        credentials.password.encode("utf-8"), settings.DEV_INBOX_PASSWORD.encode("utf-8")
    )
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


def _email_conditions(q: str | None, category: str | None) -> list[Any]:
    conds: list[Any] = []
    if q:
        like = f"%{q}%"
        conds.append(
            or_(
                col(DevEmail.to_email).ilike(like),
                col(DevEmail.subject).ilike(like),
                col(DevEmail.category).ilike(like),
            )
        )
    if category:
        conds.append(DevEmail.category == category)
    return conds


def _sms_conditions(q: str | None, category: str | None) -> list[Any]:
    conds: list[Any] = []
    if q:
        like = f"%{q}%"
        conds.append(
            or_(
                col(DevSms.to_phone).ilike(like),
                col(DevSms.body).ilike(like),
                col(DevSms.category).ilike(like),
            )
        )
    if category:
        conds.append(DevSms.category == category)
    return conds


@router.get("/emails", dependencies=[Depends(require_dev_inbox)])
async def list_emails(
    q: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    stmt = select(DevEmail).where(*_email_conditions(q, category))
    total = int(
        (await session.exec(select(func.count()).select_from(stmt.subquery()))).one()
    )
    items = (
        await session.exec(
            stmt.order_by(col(DevEmail.id).desc()).limit(limit).offset(offset)
        )
    ).all()
    return {"items": items, "total": total}


@router.get("/emails/new-count", dependencies=[Depends(require_dev_inbox)])
async def emails_new_count(
    after: int = Query(0, ge=0),
    q: str | None = Query(None),
    category: str | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    stmt = select(DevEmail).where(
        col(DevEmail.id) > after, *_email_conditions(q, category)
    )
    count = int(
        (await session.exec(select(func.count()).select_from(stmt.subquery()))).one()
    )
    return {"count": count}


@router.get("/sms", dependencies=[Depends(require_dev_inbox)])
async def list_sms(
    q: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    stmt = select(DevSms).where(*_sms_conditions(q, category))
    total = int(
        (await session.exec(select(func.count()).select_from(stmt.subquery()))).one()
    )
    items = (
        await session.exec(
            stmt.order_by(col(DevSms.id).desc()).limit(limit).offset(offset)
        )
    ).all()
    return {"items": items, "total": total}


@router.get("/sms/new-count", dependencies=[Depends(require_dev_inbox)])
async def sms_new_count(
    after: int = Query(0, ge=0),
    q: str | None = Query(None),
    category: str | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    stmt = select(DevSms).where(col(DevSms.id) > after, *_sms_conditions(q, category))
    count = int(
        (await session.exec(select(func.count()).select_from(stmt.subquery()))).one()
    )
    return {"count": count}


def _whatsapp_conditions(q: str | None, category: str | None) -> list[Any]:
    conds: list[Any] = []
    if q:
        like = f"%{q}%"
        conds.append(
            or_(
                col(DevWhatsApp.to_phone).ilike(like),
                col(DevWhatsApp.body).ilike(like),
                col(DevWhatsApp.template).ilike(like),
                col(DevWhatsApp.category).ilike(like),
            )
        )
    if category:
        conds.append(DevWhatsApp.category == category)
    return conds


@router.get("/whatsapp", dependencies=[Depends(require_dev_inbox)])
async def list_whatsapp(
    q: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    stmt = select(DevWhatsApp).where(*_whatsapp_conditions(q, category))
    total = int(
        (await session.exec(select(func.count()).select_from(stmt.subquery()))).one()
    )
    items = (
        await session.exec(
            stmt.order_by(col(DevWhatsApp.id).desc()).limit(limit).offset(offset)
        )
    ).all()
    return {"items": items, "total": total}


@router.get("/whatsapp/new-count", dependencies=[Depends(require_dev_inbox)])
async def whatsapp_new_count(
    after: int = Query(0, ge=0),
    q: str | None = Query(None),
    category: str | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    stmt = select(DevWhatsApp).where(
        col(DevWhatsApp.id) > after, *_whatsapp_conditions(q, category)
    )
    count = int(
        (await session.exec(select(func.count()).select_from(stmt.subquery()))).one()
    )
    return {"count": count}
