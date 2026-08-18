# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Return-order aggregate + the customer-facing store-credit ledger.

Three credit directions exist in this codebase; keep them straight:
  * ``CreditAccount``            — customer owes seller (postpaid)
  * ``Store.fee_credit_balance`` — platform owes seller (fee wallet)
  * ``CustomerStoreCredit``      — seller owes customer (this module)
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import DateTime, Field, UniqueConstraint

from app.models.base import BaseSchema


class ReturnStatus(str, enum.Enum):
    # Lowercase member NAMES so the native PG enum stores lowercase values
    # (matches AccountStatus / CreditAccountStatus; SQLAlchemy persists NAMES).
    awaiting_customer_confirmation = "awaiting_customer_confirmation"
    active = "active"
    awaiting_payment_confirmation = "awaiting_payment_confirmation"
    closed = "closed"
    rejected = "rejected"
    withdrawn = "withdrawn"
    expired = "expired"


TERMINAL_RETURN_STATUSES: frozenset[ReturnStatus] = frozenset(
    {
        ReturnStatus.closed,
        ReturnStatus.rejected,
        ReturnStatus.withdrawn,
        ReturnStatus.expired,
    }
)

# Statuses that keep an order line locked out of any further return. `closed`
# is deliberately here as well as in TERMINAL: the goods went back, so that
# line can never be returned again.
LINE_LOCKING_STATUSES: frozenset[ReturnStatus] = frozenset(
    {
        ReturnStatus.awaiting_customer_confirmation,
        ReturnStatus.active,
        ReturnStatus.awaiting_payment_confirmation,
        ReturnStatus.closed,
    }
)

# Statuses that mean the seller already took physical receipt.
ACCEPTED_RETURN_STATUSES: frozenset[ReturnStatus] = frozenset(
    {ReturnStatus.awaiting_payment_confirmation, ReturnStatus.closed}
)


class ReturnInitiator(str, enum.Enum):
    customer = "customer"
    seller = "seller"
    admin = "admin"


class ReturnSettlementChoice(str, enum.Enum):
    payment = "payment"
    store_credit = "store_credit"


class ReturnReasonCode(str, enum.Enum):
    damaged = "damaged"
    wrong_item = "wrong_item"
    past_expiry = "past_expiry"
    quality_issue = "quality_issue"
    not_as_described = "not_as_described"
    other = "other"


class StoreCreditEntryType(str, enum.Enum):
    return_credit = "return_credit"
    order_applied = "order_applied"
    order_reverted = "order_reverted"
    admin_adjust = "admin_adjust"


class ReturnRequest(BaseSchema, table=True):
    """One return request against one delivered order."""

    __tablename__ = "return_request"
    __table_args__ = (
        Index("ix_return_request_customer_created", "customer_profile_id", "created_at"),
        Index("ix_return_request_seller_status", "seller_profile_id", "status"),
        Index("ix_return_request_store_status", "store_id", "status"),
    )

    order_id: int = Field(foreign_key="order.id", nullable=False, index=True)
    customer_profile_id: int = Field(
        foreign_key="customerprofile.id", nullable=False, index=True
    )
    # Denormalised so seller/admin queues filter without joining `order`.
    store_id: int = Field(foreign_key="store.id", nullable=False, index=True)
    seller_profile_id: int = Field(
        foreign_key="sellerprofile.id", nullable=False, index=True
    )
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)

    initiated_by: ReturnInitiator = Field(nullable=False)
    # No FK: history survives user deletion (mirrors admin_action_log).
    initiated_by_user_id: int = Field(nullable=False)

    status: ReturnStatus = Field(
        default=ReturnStatus.awaiting_customer_confirmation, nullable=False, index=True
    )
    is_full_order: bool = Field(default=False, nullable=False)

    reason_code: ReturnReasonCode = Field(nullable=False)
    reason_note: Optional[str] = Field(default=None, max_length=500)

    items_amount: float = Field(nullable=False)
    delivery_fee_amount: float = Field(default=0.0, nullable=False)
    total_amount: float = Field(nullable=False)

    settlement_choice: ReturnSettlementChoice = Field(nullable=False)
    credit_reversal_amount: float = Field(default=0.0, nullable=False)
    store_credit_amount: float = Field(default=0.0, nullable=False)
    payment_amount: float = Field(default=0.0, nullable=False)

    agreement_policy_version: int = Field(nullable=False)
    agreement_accepted_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )

    window_expires_at: datetime = Field(  # type: ignore[call-overload]
        nullable=False, sa_type=DateTime(timezone=True)
    )
    confirm_expires_at: datetime = Field(  # type: ignore[call-overload]
        nullable=False, sa_type=DateTime(timezone=True)
    )
    handover_expires_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )

    receipt_otp: Optional[str] = Field(default=None, max_length=6)
    receipt_otp_attempts: int = Field(default=0, nullable=False)
    receipt_otp_sent_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    receipt_otp_verified_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )

    restock: bool = Field(default=False, nullable=False)
    rejection_reason: Optional[str] = Field(default=None, max_length=500)

    decided_by_user_id: Optional[int] = Field(default=None)
    closed_by_user_id: Optional[int] = Field(default=None)

    confirmed_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    decided_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    closed_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )


class ReturnRequestItem(BaseSchema, table=True):
    """One complete order line inside a return. Partial quantities are refused."""

    __tablename__ = "return_request_item"
    __table_args__ = (
        UniqueConstraint(
            "return_request_id", "order_item_id", name="uq_return_item_request_orderitem"
        ),
    )

    return_request_id: int = Field(
        foreign_key="return_request.id", nullable=False, index=True
    )
    order_item_id: int = Field(foreign_key="orderitem.id", nullable=False, index=True)
    quantity: int = Field(nullable=False)
    product_name_snapshot: str = Field(nullable=False)
    unit_price_snapshot: float = Field(nullable=False)
    line_total: float = Field(nullable=False)


class ReturnEvent(BaseSchema, table=True):
    """Append-only transition log — the BRD audit requirement."""

    __tablename__ = "return_event"
    __table_args__ = (
        Index("ix_return_event_request_created", "return_request_id", "created_at"),
    )

    return_request_id: int = Field(
        foreign_key="return_request.id", nullable=False, index=True
    )
    from_status: Optional[ReturnStatus] = Field(default=None)
    to_status: ReturnStatus = Field(nullable=False)
    # customer / seller / admin / system
    actor_role: str = Field(nullable=False, max_length=16)
    actor_user_id: Optional[int] = Field(default=None)
    note: Optional[str] = Field(default=None, max_length=500)


class CustomerStoreCredit(BaseSchema, table=True):
    """Seller-owes-customer balance. Cached; the entry ledger is the truth."""

    __tablename__ = "customer_store_credit"
    __table_args__ = (
        UniqueConstraint(
            "seller_profile_id", "customer_profile_id",
            name="uq_customer_store_credit_pair",
        ),
        Index("ix_customer_store_credit_customer", "customer_profile_id"),
    )

    seller_profile_id: int = Field(
        foreign_key="sellerprofile.id", nullable=False, index=True
    )
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False)
    balance: float = Field(default=0.0, nullable=False)
    lifetime_earned: float = Field(default=0.0, nullable=False)
    lifetime_spent: float = Field(default=0.0, nullable=False)


class CustomerStoreCreditEntry(BaseSchema, table=True):
    """Append-only ledger for ``CustomerStoreCredit``."""

    __tablename__ = "customer_store_credit_entry"
    __table_args__ = (
        Index(
            "ix_customer_store_credit_entry_acct_created", "account_id", "created_at"
        ),
    )

    account_id: int = Field(
        foreign_key="customer_store_credit.id", nullable=False, index=True
    )
    entry_type: StoreCreditEntryType = Field(nullable=False)
    amount: float = Field(nullable=False)  # signed
    balance_after: float = Field(nullable=False)
    return_request_id: Optional[int] = Field(
        default=None, foreign_key="return_request.id"
    )
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    note: Optional[str] = Field(default=None, max_length=300)
    actor_user_id: Optional[int] = Field(default=None)
