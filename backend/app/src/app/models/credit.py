# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import enum
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, UniqueConstraint

from app.models.base import BaseSchema


class CreditAccountStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"


class CreditEntryType(str, enum.Enum):
    charge = "charge"
    repayment = "repayment"
    reversal = "reversal"


class SellerCreditConfig(BaseSchema, table=True):
    """Admin-managed per-seller credit gate + ceiling. One row per seller."""

    __tablename__ = "seller_credit_config"
    __table_args__ = (
        UniqueConstraint("seller_profile_id", name="uq_seller_credit_config_seller"),
    )

    seller_profile_id: int = Field(
        foreign_key="sellerprofile.id", nullable=False, index=True
    )
    credit_enabled: bool = Field(default=False, nullable=False)
    max_limit_per_customer: float = Field(default=0.0, nullable=False)


class CreditAccount(BaseSchema, table=True):
    """A revolving credit relationship between a seller and a customer.

    ``outstanding_balance`` is a denormalized running total (source of truth for
    real-time blocking); it is always mutated in the same transaction as the
    corresponding ``CreditLedgerEntry``. ``available = credit_limit - outstanding_balance``.
    """

    __tablename__ = "credit_account"
    __table_args__ = (
        UniqueConstraint(
            "seller_profile_id", "customer_profile_id", name="uq_credit_account_pair"
        ),
        Index("ix_credit_account_customer", "customer_profile_id"),
    )

    seller_profile_id: int = Field(
        foreign_key="sellerprofile.id", nullable=False, index=True
    )
    customer_profile_id: int = Field(
        foreign_key="customerprofile.id", nullable=False
    )
    credit_limit: float = Field(nullable=False)
    outstanding_balance: float = Field(default=0.0, nullable=False)
    status: CreditAccountStatus = Field(
        default=CreditAccountStatus.active, nullable=False
    )
    granted_by_user_id: int = Field(nullable=False)
    last_notified_threshold: int = Field(default=0, nullable=False)


class CreditLedgerEntry(BaseSchema, table=True):
    """Append-only financial history: one row per charge / repayment / reversal."""

    __tablename__ = "credit_ledger_entry"
    __table_args__ = (
        Index("ix_credit_ledger_account_created", "credit_account_id", "created_at"),
    )

    credit_account_id: int = Field(
        foreign_key="credit_account.id", nullable=False, index=True
    )
    entry_type: CreditEntryType = Field(nullable=False)
    amount: float = Field(nullable=False)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    balance_after: float = Field(nullable=False)
    note: Optional[str] = Field(default=None, max_length=300)
    recorded_by_user_id: Optional[int] = Field(default=None)
