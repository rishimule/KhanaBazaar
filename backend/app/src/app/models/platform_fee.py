# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Platform-fee data model: global settings, per-service config, subscription
plan prices, and the per-(store, service) fee arrangement + its payments/events.

Native PG enums store the lowercase VALUES (via `values_callable`) so labels stay
snake_case while Python members stay PascalCase — mirrors
`seller_profile_change_request`. All enums (incl. Phase-2 values) are defined now
so Phase 2 never needs `ALTER TYPE ADD VALUE`."""
import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, UniqueConstraint

from app.models.base import BaseSchema


class FeeModel(str, enum.Enum):
    Freebie = "freebie"
    Subscription = "subscription"
    OrderValuePercent = "order_value_percent"
    PayPerTransaction = "pay_per_transaction"


class ArrangementStatus(str, enum.Enum):
    Trial = "trial"
    PendingActivation = "pending_activation"
    Active = "active"
    Grace = "grace"
    Suspended = "suspended"


class FeePaymentKind(str, enum.Enum):
    SubscriptionFee = "subscription_fee"
    SecurityDeposit = "security_deposit"
    PayPerTxnTopUp = "pay_per_txn_topup"
    OrderValueInvoice = "order_value_invoice"


class FeePaymentStatus(str, enum.Enum):
    Pending = "pending"
    Confirmed = "confirmed"
    Rejected = "rejected"


class FeeEventType(str, enum.Enum):
    ArrangementCreated = "arrangement_created"
    ModelChanged = "model_changed"
    Activated = "activated"
    Extended = "extended"
    Renewed = "renewed"
    TrialHeld = "trial_held"
    ReminderSent = "reminder_sent"
    GraceStarted = "grace_started"
    Suspended = "suspended"
    Reactivated = "reactivated"
    Terminated = "terminated"
    PaymentRecorded = "payment_recorded"
    PaymentConfirmed = "payment_confirmed"
    PaymentRejected = "payment_rejected"
    DepositRecorded = "deposit_recorded"
    DepositForfeited = "deposit_forfeited"
    DepositRefunded = "deposit_refunded"
    BalanceTopup = "balance_topup"
    BalanceDeducted = "balance_deducted"
    BalanceRefunded = "balance_refunded"
    InvoiceIssued = "invoice_issued"
    InvoicePaid = "invoice_paid"
    InvoiceWaived = "invoice_waived"


class StoreCreditReason(str, enum.Enum):
    GrantedOnExit = "granted_on_exit"
    AppliedToFee = "applied_to_fee"
    AdminCashOut = "admin_cash_out"
    AdminAdjust = "admin_adjust"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Serialize enum members by VALUE, not NAME (snake_case PG labels)."""
    return [m.value for m in enum_cls]


# `feemodel` is referenced by two columns of fee_arrangement (model + queued_model).
# Share ONE type instance so create_all emits a single CREATE TYPE for the table
# (two separate SAEnum instances with the same name risk a duplicate CREATE TYPE).
_FEE_MODEL_SA = SAEnum(
    FeeModel, name="feemodel", values_callable=_enum_values, create_type=False
)


class PlatformFeeSettings(BaseSchema, table=True):
    __tablename__ = "platform_fee_settings"
    grace_period_days: int = Field(default=2, nullable=False)
    expiry_reminder_start_days: int = Field(default=7, nullable=False)
    pending_payment_protect_days: int = Field(default=7, nullable=False)
    bank_account_name: Optional[str] = Field(default=None, max_length=140)
    bank_account_number: Optional[str] = Field(default=None, max_length=40)
    bank_ifsc: Optional[str] = Field(default=None, max_length=20)
    upi_id: Optional[str] = Field(default=None, max_length=100)
    qr_image_url: Optional[str] = Field(default=None, max_length=500)
    qr_storage_key: Optional[str] = Field(default=None, max_length=300)
    gstin: Optional[str] = Field(default=None, max_length=20)


class ServiceFeeConfig(BaseSchema, table=True):
    __tablename__ = "service_fee_config"
    __table_args__ = (
        UniqueConstraint("service_id", name="uq_service_fee_config_service"),
    )
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)
    freebie_enabled: bool = Field(default=True, nullable=False)
    freebie_default_days: int = Field(default=30, nullable=False)
    subscription_enabled: bool = Field(default=False, nullable=False)
    order_value_enabled: bool = Field(default=False, nullable=False)
    order_value_percent: float = Field(default=0.0, nullable=False)
    order_value_min_deposit: float = Field(default=0.0, nullable=False)
    order_value_billing_day: int = Field(default=5, nullable=False)
    pay_per_txn_enabled: bool = Field(default=False, nullable=False)
    pay_per_txn_fee: float = Field(default=0.0, nullable=False)
    pay_per_txn_min_deposit: float = Field(default=0.0, nullable=False)
    pay_per_txn_low_balance_threshold: float = Field(default=0.0, nullable=False)


class ServiceSubscriptionPlan(BaseSchema, table=True):
    __tablename__ = "service_subscription_plan"
    __table_args__ = (
        UniqueConstraint(
            "service_id", "duration_months", name="uq_service_subscription_plan"
        ),
    )
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)
    duration_months: int = Field(nullable=False)  # 3, 6, or 12
    price: float = Field(default=0.0, nullable=False)
    is_active: bool = Field(default=True, nullable=False)


class FeeArrangement(BaseSchema, table=True):
    __tablename__ = "fee_arrangement"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "service_id", name="uq_fee_arrangement_store_service"
        ),
    )
    store_id: int = Field(foreign_key="store.id", nullable=False, index=True)
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)
    model: FeeModel = Field(
        sa_column=Column(_FEE_MODEL_SA, nullable=False)
    )
    status: ArrangementStatus = Field(
        sa_column=Column(
            SAEnum(
                ArrangementStatus,
                name="arrangementstatus",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
            index=True,
        )
    )
    valid_until: Optional[date] = Field(default=None)
    subscription_duration_months: Optional[int] = Field(default=None)
    price_snapshot: Optional[float] = Field(default=None)
    security_deposit_amount: float = Field(default=0.0, nullable=False)
    balance: float = Field(default=0.0, nullable=False)
    auto_renew: bool = Field(default=True, nullable=False)
    cancel_requested: bool = Field(default=False, nullable=False)
    queued_model: Optional[FeeModel] = Field(
        default=None,
        sa_column=Column(_FEE_MODEL_SA, nullable=True),
    )
    queued_duration_months: Optional[int] = Field(default=None)
    queued_effective_date: Optional[date] = Field(default=None)
    pending_since: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    last_reminder_sent_on: Optional[date] = Field(default=None)
    suspended_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    suspended_reason: Optional[str] = Field(default=None, max_length=200)


class FeePayment(BaseSchema, table=True):
    __tablename__ = "fee_payment"
    arrangement_id: int = Field(foreign_key="fee_arrangement.id", nullable=False, index=True)
    kind: FeePaymentKind = Field(
        sa_column=Column(
            SAEnum(
                FeePaymentKind,
                name="feepaymentkind",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
        )
    )
    amount: float = Field(nullable=False)
    status: FeePaymentStatus = Field(
        default=FeePaymentStatus.Pending,
        sa_column=Column(
            SAEnum(
                FeePaymentStatus,
                name="feepaymentstatus",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
            index=True,
        ),
    )
    seller_note: Optional[str] = Field(default=None, max_length=200)
    confirmed_by_admin_id: Optional[int] = Field(default=None, foreign_key="user.id")
    confirmed_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
    reject_reason: Optional[str] = Field(default=None, max_length=200)


class FeeEvent(BaseSchema, table=True):
    __tablename__ = "fee_event"
    arrangement_id: int = Field(foreign_key="fee_arrangement.id", nullable=False, index=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id", index=True)
    event_type: FeeEventType = Field(
        sa_column=Column(
            SAEnum(
                FeeEventType,
                name="feeeventtype",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
        )
    )
    amount_delta: Optional[float] = Field(default=None)
    note: Optional[str] = Field(default=None, max_length=300)
    actor: Optional[str] = Field(default=None, max_length=60)


class StoreCreditEvent(BaseSchema, table=True):
    __tablename__ = "store_credit_event"
    store_id: int = Field(foreign_key="store.id", nullable=False, index=True)
    amount_delta: float = Field(nullable=False)
    reason: StoreCreditReason = Field(
        sa_column=Column(
            SAEnum(
                StoreCreditReason,
                name="storecreditreason",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
        )
    )
    related_arrangement_id: Optional[int] = Field(
        default=None, foreign_key="fee_arrangement.id"
    )
    related_payment_id: Optional[int] = Field(
        default=None, foreign_key="fee_payment.id"
    )
    actor: Optional[str] = Field(default=None, max_length=60)
    note: Optional[str] = Field(default=None, max_length=300)
