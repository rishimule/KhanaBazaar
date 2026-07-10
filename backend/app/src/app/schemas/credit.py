# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreditConfigRead(BaseModel):
    credit_enabled: bool
    max_limit_per_customer: float
    model_config = {"from_attributes": True}


class AdminCreditConfigPatch(BaseModel):
    credit_enabled: Optional[bool] = None
    max_limit_per_customer: Optional[float] = Field(default=None, ge=0)


class GrantCreditRequest(BaseModel):
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    credit_limit: float = Field(gt=0)


class CreditAccountPatch(BaseModel):
    credit_limit: Optional[float] = Field(default=None, gt=0)
    status: Optional[str] = None  # "active" | "suspended"


class RepaymentRequest(BaseModel):
    amount: float = Field(gt=0)
    note: Optional[str] = Field(default=None, max_length=300)


class CreditAccountRead(BaseModel):
    id: int
    customer_profile_id: int
    seller_profile_id: int
    credit_limit: float
    outstanding_balance: float
    available: float
    status: str
    created_at: datetime


class CreditLedgerEntryRead(BaseModel):
    id: int
    entry_type: str
    amount: float
    order_id: Optional[int]
    balance_after: float
    note: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class CustomerCreditAccountRead(BaseModel):
    seller_profile_id: int
    store_name: str
    credit_limit: float
    outstanding_balance: float
    available: float
    status: str


class CreditEligibilityRead(BaseModel):
    eligible: bool
    available: float
    credit_limit: float
    outstanding_balance: float


def to_account_read(acct: "object") -> CreditAccountRead:
    """Build a CreditAccountRead from a CreditAccount ORM row, computing available."""
    return CreditAccountRead(
        id=acct.id,  # type: ignore[attr-defined]
        customer_profile_id=acct.customer_profile_id,  # type: ignore[attr-defined]
        seller_profile_id=acct.seller_profile_id,  # type: ignore[attr-defined]
        credit_limit=acct.credit_limit,  # type: ignore[attr-defined]
        outstanding_balance=acct.outstanding_balance,  # type: ignore[attr-defined]
        available=round(acct.credit_limit - acct.outstanding_balance, 2),  # type: ignore[attr-defined]
        status=acct.status.value,  # type: ignore[attr-defined]
        created_at=acct.created_at,  # type: ignore[attr-defined]
    )
