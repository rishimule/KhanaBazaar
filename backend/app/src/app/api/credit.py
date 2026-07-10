# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import get_current_admin, get_current_seller
from app.db.session import get_db_session
from app.models.base import User
from app.models.credit import CreditAccount, CreditAccountStatus
from app.models.profile import SellerProfile
from app.schemas.credit import (
    AdminCreditConfigPatch,
    CreditAccountPatch,
    CreditAccountRead,
    CreditConfigRead,
    CreditLedgerEntryRead,
    GrantCreditRequest,
    RepaymentRequest,
    to_account_read,
)
from app.schemas.pagination import PagedResponse
from app.services import credit as svc

admin_router = APIRouter()
router = APIRouter()


async def _seller_profile_id(session: AsyncSession, user: User) -> int:
    profile = (
        await session.exec(select(SellerProfile).where(SellerProfile.user_id == user.id))
    ).first()
    if profile is None or profile.id is None:
        raise HTTPException(status_code=404, detail={"error": "seller_not_found"})
    return profile.id


async def _owned_account(
    session: AsyncSession, account_id: int, seller_profile_id: int
) -> CreditAccount:
    acct = await svc.get_account(session, account_id)
    if acct is None or acct.seller_profile_id != seller_profile_id:
        raise HTTPException(status_code=404, detail={"error": "account_not_found"})
    return acct


@router.get("/config", response_model=CreditConfigRead)
async def seller_get_config(
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> CreditConfigRead:
    spid = await _seller_profile_id(session, seller)
    return CreditConfigRead.model_validate(await svc.load_seller_credit_config(session, spid))


@router.get("/accounts", response_model=list[CreditAccountRead])
async def seller_list_accounts(
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> list[CreditAccountRead]:
    spid = await _seller_profile_id(session, seller)
    return [to_account_read(a) for a in await svc.list_seller_accounts(session, spid)]


@router.post("/accounts", response_model=CreditAccountRead, status_code=201)
async def seller_grant_credit(
    body: GrantCreditRequest,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> CreditAccountRead:
    assert seller.id is not None
    spid = await _seller_profile_id(session, seller)
    customer = await svc.resolve_customer(
        session, phone=body.customer_phone, email=body.customer_email
    )
    assert customer.id is not None
    acct = await svc.grant_credit(
        session,
        seller_profile_id=spid,
        granted_by_user_id=seller.id,
        customer_profile_id=customer.id,
        credit_limit=body.credit_limit,
    )
    # Task 10 wires notify_credit_granted(session, acct) here (best-effort).
    return to_account_read(acct)


@router.patch("/accounts/{account_id}", response_model=CreditAccountRead)
async def seller_patch_account(
    account_id: int,
    body: CreditAccountPatch,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> CreditAccountRead:
    spid = await _seller_profile_id(session, seller)
    acct = await _owned_account(session, account_id, spid)
    status_enum = None
    if body.status is not None:
        try:
            status_enum = CreditAccountStatus(body.status)
        except ValueError:
            raise HTTPException(status_code=422, detail={"error": "invalid_status"}) from None
    acct = await svc.adjust_credit_account(
        session, account=acct, credit_limit=body.credit_limit, status=status_enum
    )
    return to_account_read(acct)


@router.post("/accounts/{account_id}/repayments", response_model=CreditLedgerEntryRead)
async def seller_record_repayment(
    account_id: int,
    body: RepaymentRequest,
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> CreditLedgerEntryRead:
    assert seller.id is not None
    spid = await _seller_profile_id(session, seller)
    acct = await _owned_account(session, account_id, spid)
    entry = await svc.record_repayment(
        session, account=acct, amount=body.amount, note=body.note,
        recorded_by_user_id=seller.id,
    )
    return CreditLedgerEntryRead.model_validate(entry)


@router.get(
    "/accounts/{account_id}/ledger", response_model=PagedResponse[CreditLedgerEntryRead]
)
async def seller_get_ledger(
    account_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    seller: User = Depends(get_current_seller),
    session: AsyncSession = Depends(get_db_session),
) -> PagedResponse[CreditLedgerEntryRead]:
    spid = await _seller_profile_id(session, seller)
    await _owned_account(session, account_id, spid)
    items, total = await svc.list_ledger(session, account_id, page, page_size)
    return PagedResponse(
        items=[CreditLedgerEntryRead.model_validate(e) for e in items],
        total=total, page=page, page_size=page_size,
    )


@admin_router.get(
    "/sellers/{seller_id}/credit-config", response_model=CreditConfigRead
)
async def admin_get_credit_config(
    seller_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> CreditConfigRead:
    row = await svc.load_seller_credit_config(session, seller_id)
    return CreditConfigRead.model_validate(row)


@admin_router.patch(
    "/sellers/{seller_id}/credit-config", response_model=CreditConfigRead
)
async def admin_patch_credit_config(
    seller_id: int,
    body: AdminCreditConfigPatch,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
) -> CreditConfigRead:
    assert admin.id is not None
    row = await svc.admin_set_credit_config(
        session,
        seller_profile_id=seller_id,
        admin_user_id=admin.id,
        credit_enabled=body.credit_enabled,
        max_limit_per_customer=body.max_limit_per_customer,
    )
    return CreditConfigRead.model_validate(row)
