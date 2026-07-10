# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Credit-customers service: admin config, grant/adjust/repayment ledger,
checkout charge/reversal, and eligibility. The platform is a ledger +
enforcement layer only — no money moves for credit."""
from typing import Optional

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.otp import InvalidPhoneNumber, normalize_email, normalize_phone
from app.models.admin_audit import AdminActionTargetType
from app.models.base import User, UserRole
from app.models.credit import (
    CreditAccount,
    CreditAccountStatus,
    CreditEntryType,
    CreditLedgerEntry,
    SellerCreditConfig,
)
from app.models.profile import CustomerProfile
from app.models.store import Store
from app.services import admin_audit

# ─── Admin per-seller config ─────────────────────────────────────────────


async def load_seller_credit_config(
    session: AsyncSession, seller_profile_id: int
) -> SellerCreditConfig:
    """The seller's config row, or a transient default (unsaved) if none yet."""
    row = (
        await session.exec(
            select(SellerCreditConfig).where(
                SellerCreditConfig.seller_profile_id == seller_profile_id
            )
        )
    ).first()
    return row or SellerCreditConfig(seller_profile_id=seller_profile_id)


async def get_or_create_seller_credit_config(
    session: AsyncSession, seller_profile_id: int
) -> SellerCreditConfig:
    row = (
        await session.exec(
            select(SellerCreditConfig).where(
                SellerCreditConfig.seller_profile_id == seller_profile_id
            )
        )
    ).first()
    if row is None:
        row = SellerCreditConfig(seller_profile_id=seller_profile_id)
        session.add(row)
        await session.flush()
    return row


async def admin_set_credit_config(
    session: AsyncSession,
    *,
    seller_profile_id: int,
    admin_user_id: int,
    credit_enabled: Optional[bool] = None,
    max_limit_per_customer: Optional[float] = None,
) -> SellerCreditConfig:
    row = await get_or_create_seller_credit_config(session, seller_profile_id)
    before = {
        "credit_enabled": row.credit_enabled,
        "max_limit_per_customer": row.max_limit_per_customer,
    }
    if credit_enabled is not None:
        row.credit_enabled = credit_enabled
    if max_limit_per_customer is not None:
        if max_limit_per_customer < 0:
            raise HTTPException(status_code=422, detail={"error": "invalid_cap"})
        row.max_limit_per_customer = max_limit_per_customer
    session.add(row)
    await session.flush()
    await admin_audit.log(
        session=session,
        admin_user_id=admin_user_id,
        target_seller_id=seller_profile_id,
        target_type=AdminActionTargetType.SellerProfile,
        target_id=seller_profile_id,
        action="credit.set_config",
        before_json=before,
        after_json={
            "credit_enabled": row.credit_enabled,
            "max_limit_per_customer": row.max_limit_per_customer,
        },
    )
    await session.commit()
    await session.refresh(row)
    return row


# ─── Customer lookup ─────────────────────────────────────────────────────


async def resolve_customer(
    session: AsyncSession,
    *,
    phone: Optional[str] = None,
    email: Optional[str] = None,
) -> CustomerProfile:
    """Find an existing Customer by exactly one of phone/email. Email lives on
    User (CustomerProfile has none), so email lookups join through User."""
    if bool(phone) == bool(email):
        raise HTTPException(status_code=422, detail={"error": "exactly_one_contact"})
    if email:
        norm = normalize_email(email)
        prof = (
            await session.exec(
                select(CustomerProfile)
                .join(User, User.id == CustomerProfile.user_id)  # type: ignore[arg-type]
                .where(User.email == norm, User.role == UserRole.Customer)
            )
        ).first()
    else:
        try:
            norm = normalize_phone(phone or "")
        except InvalidPhoneNumber:
            raise HTTPException(
                status_code=422, detail={"error": "invalid_phone"}
            ) from None
        prof = (
            await session.exec(
                select(CustomerProfile).where(CustomerProfile.phone == norm)
            )
        ).first()
    if prof is None:
        raise HTTPException(status_code=404, detail={"error": "customer_not_found"})
    return prof


# ─── Ledger + grant / adjust / repayment ─────────────────────────────────


async def _append_entry(
    session: AsyncSession,
    account: CreditAccount,
    entry_type: CreditEntryType,
    amount: float,
    balance_after: float,
    *,
    order_id: Optional[int] = None,
    note: Optional[str] = None,
    recorded_by: Optional[int] = None,
) -> CreditLedgerEntry:
    entry = CreditLedgerEntry(
        credit_account_id=account.id,
        entry_type=entry_type,
        amount=amount,
        balance_after=balance_after,
        order_id=order_id,
        note=note,
        recorded_by_user_id=recorded_by,
    )
    session.add(entry)
    await session.flush()
    return entry


async def grant_credit(
    session: AsyncSession,
    *,
    seller_profile_id: int,
    granted_by_user_id: int,
    customer_profile_id: int,
    credit_limit: float,
) -> CreditAccount:
    if credit_limit <= 0:
        raise HTTPException(status_code=422, detail={"error": "invalid_limit"})
    cfg = await load_seller_credit_config(session, seller_profile_id)
    if not cfg.credit_enabled:
        raise HTTPException(status_code=409, detail={"error": "credit_not_enabled"})
    if credit_limit > cfg.max_limit_per_customer:
        raise HTTPException(status_code=422, detail={"error": "limit_exceeds_cap"})
    existing = (
        await session.exec(
            select(CreditAccount).where(
                CreditAccount.seller_profile_id == seller_profile_id,
                CreditAccount.customer_profile_id == customer_profile_id,
            )
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail={"error": "account_exists"})
    acct = CreditAccount(
        seller_profile_id=seller_profile_id,
        customer_profile_id=customer_profile_id,
        credit_limit=credit_limit,
        outstanding_balance=0.0,
        status=CreditAccountStatus.active,
        granted_by_user_id=granted_by_user_id,
    )
    session.add(acct)
    await session.commit()
    await session.refresh(acct)
    return acct


async def adjust_credit_account(
    session: AsyncSession,
    *,
    account: CreditAccount,
    credit_limit: Optional[float] = None,
    status: Optional[CreditAccountStatus] = None,
) -> CreditAccount:
    # Lock the row AND repopulate the instance's attributes (a plain
    # with_for_update SELECT would return the identity-mapped, still-stale
    # object) so a concurrent checkout charge can't be clobbered by an absolute
    # write from a stale in-memory copy.
    await session.refresh(account, with_for_update=True)
    if credit_limit is not None:
        if credit_limit <= 0:
            raise HTTPException(status_code=422, detail={"error": "invalid_limit"})
        if credit_limit < account.outstanding_balance:
            raise HTTPException(status_code=422, detail={"error": "below_outstanding"})
        # Grandfather: an existing limit may stay above a lowered cap, but a
        # *raise* must fit within the seller's current cap.
        if credit_limit > account.credit_limit:
            cfg = await load_seller_credit_config(session, account.seller_profile_id)
            if credit_limit > cfg.max_limit_per_customer:
                raise HTTPException(
                    status_code=422, detail={"error": "limit_exceeds_cap"}
                )
        account.credit_limit = credit_limit
    if status is not None:
        account.status = status
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def record_repayment(
    session: AsyncSession,
    *,
    account: CreditAccount,
    amount: float,
    note: Optional[str],
    recorded_by_user_id: int,
) -> CreditLedgerEntry:
    # Lock the row AND repopulate the instance (a plain with_for_update SELECT
    # returns the identity-mapped, still-stale object) so a concurrent checkout
    # charge isn't clobbered by an absolute write from a stale in-memory copy.
    await session.refresh(account, with_for_update=True)
    if amount <= 0:
        raise HTTPException(status_code=422, detail={"error": "invalid_amount"})
    if amount > account.outstanding_balance:
        raise HTTPException(status_code=422, detail={"error": "over_repayment"})
    account.outstanding_balance = round(account.outstanding_balance - amount, 2)
    session.add(account)
    entry = await _append_entry(
        session,
        account,
        CreditEntryType.repayment,
        amount,
        account.outstanding_balance,
        note=note,
        recorded_by=recorded_by_user_id,
    )
    await session.commit()
    await session.refresh(entry)
    return entry


async def get_account(
    session: AsyncSession, account_id: int
) -> Optional[CreditAccount]:
    return (
        await session.exec(select(CreditAccount).where(CreditAccount.id == account_id))
    ).first()


async def list_seller_accounts(
    session: AsyncSession, seller_profile_id: int
) -> list[CreditAccount]:
    return list(
        (
            await session.exec(
                select(CreditAccount)
                .where(CreditAccount.seller_profile_id == seller_profile_id)
                .order_by(CreditAccount.created_at.desc())  # type: ignore[attr-defined]
            )
        ).all()
    )


async def list_ledger(
    session: AsyncSession, credit_account_id: int, page: int, page_size: int
) -> tuple[list[CreditLedgerEntry], int]:
    total = len(
        (
            await session.exec(
                select(CreditLedgerEntry.id).where(
                    CreditLedgerEntry.credit_account_id == credit_account_id
                )
            )
        ).all()
    )
    items = list(
        (
            await session.exec(
                select(CreditLedgerEntry)
                .where(CreditLedgerEntry.credit_account_id == credit_account_id)
                .order_by(CreditLedgerEntry.created_at.desc())  # type: ignore[attr-defined]
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return items, total


# ─── Checkout: eligibility + charge / reversal ───────────────────────────


async def resolve_seller_id_for_store(
    session: AsyncSession, store_id: int
) -> Optional[int]:
    return (
        await session.exec(select(Store.seller_profile_id).where(Store.id == store_id))
    ).first()


async def lock_credit_account(
    session: AsyncSession, seller_profile_id: int, customer_profile_id: int
) -> Optional[CreditAccount]:
    """Row-lock the (seller, customer) credit account to serialize concurrent
    charges and prevent overspend races."""
    return (
        await session.exec(
            select(CreditAccount)
            .where(
                CreditAccount.seller_profile_id == seller_profile_id,
                CreditAccount.customer_profile_id == customer_profile_id,
            )
            .with_for_update()
        )
    ).first()


async def assert_credit_eligible(
    session: AsyncSession, *, store_id: int, customer_profile_id: int, total: float
) -> CreditAccount:
    """Lock + validate credit availability for a checkout. Raises 409 on any
    ineligibility; returns the locked account for the caller to charge."""
    seller_id = await resolve_seller_id_for_store(session, store_id)
    if seller_id is None:
        raise HTTPException(status_code=409, detail={"error": "credit_not_available"})
    cfg = await load_seller_credit_config(session, seller_id)
    acct = await lock_credit_account(session, seller_id, customer_profile_id)
    if (
        acct is None
        or acct.status != CreditAccountStatus.active
        or not cfg.credit_enabled
    ):
        raise HTTPException(status_code=409, detail={"error": "credit_not_available"})
    if total > round(acct.credit_limit - acct.outstanding_balance, 2):
        raise HTTPException(status_code=409, detail={"error": "insufficient_credit"})
    return acct


async def charge_credit_account(
    session: AsyncSession, *, account: CreditAccount, order_id: int, amount: float
) -> None:
    """Increment outstanding + append a charge ledger row. Caller already holds
    the row lock (via assert_credit_eligible) and owns the transaction."""
    account.outstanding_balance = round(account.outstanding_balance + amount, 2)
    session.add(account)
    await _append_entry(
        session, account, CreditEntryType.charge, amount,
        account.outstanding_balance, order_id=order_id,
    )


async def reverse_credit_charge(
    session: AsyncSession, *, store_id: int, customer_profile_id: int,
    order_id: int, amount: float,
) -> None:
    """Reverse a credit charge on order cancel/refund: decrement outstanding
    (floored at 0) + append a reversal ledger row. Best-effort no-op if no
    account. Caller owns the transaction."""
    seller_id = await resolve_seller_id_for_store(session, store_id)
    if seller_id is None:
        return
    acct = await lock_credit_account(session, seller_id, customer_profile_id)
    if acct is None:
        return
    acct.outstanding_balance = max(0.0, round(acct.outstanding_balance - amount, 2))
    session.add(acct)
    await _append_entry(
        session, acct, CreditEntryType.reversal, amount,
        acct.outstanding_balance, order_id=order_id,
    )


async def credit_eligibility(
    session: AsyncSession, *, customer_profile_id: int, store_id: int, cart_total: float
) -> dict:  # type: ignore[type-arg]
    """Non-locking, display-only credit standing for a checkout. Never raises;
    returns eligible=False when there's no usable credit. The authoritative
    check is the row-locked assert_credit_eligible at checkout time."""
    zero = {
        "eligible": False,
        "available": 0.0,
        "credit_limit": 0.0,
        "outstanding_balance": 0.0,
    }
    seller_id = await resolve_seller_id_for_store(session, store_id)
    if seller_id is None:
        return zero
    cfg = await load_seller_credit_config(session, seller_id)
    acct = (
        await session.exec(
            select(CreditAccount).where(
                CreditAccount.seller_profile_id == seller_id,
                CreditAccount.customer_profile_id == customer_profile_id,
            )
        )
    ).first()
    if acct is None or acct.status != CreditAccountStatus.active or not cfg.credit_enabled:
        return zero
    available = round(acct.credit_limit - acct.outstanding_balance, 2)
    return {
        "eligible": cart_total <= available,
        "available": available,
        "credit_limit": acct.credit_limit,
        "outstanding_balance": acct.outstanding_balance,
    }
