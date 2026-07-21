# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Optional

from pydantic import BaseModel, Field


class PlatformFeeSettingsRead(BaseModel):
    grace_period_days: int
    expiry_reminder_start_days: int
    pending_payment_protect_days: int
    bank_account_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    upi_id: Optional[str] = None
    qr_image_url: Optional[str] = None
    gstin: Optional[str] = None


class PlatformFeeSettingsPatch(BaseModel):
    grace_period_days: Optional[int] = Field(default=None, ge=0, le=30)
    expiry_reminder_start_days: Optional[int] = Field(default=None, ge=1, le=30)
    pending_payment_protect_days: Optional[int] = Field(default=None, ge=0, le=60)
    bank_account_name: Optional[str] = Field(default=None, max_length=140)
    bank_account_number: Optional[str] = Field(default=None, max_length=40)
    bank_ifsc: Optional[str] = Field(default=None, max_length=20)
    upi_id: Optional[str] = Field(default=None, max_length=100)
    qr_image_url: Optional[str] = Field(default=None, max_length=500)
    gstin: Optional[str] = Field(default=None, max_length=20)


class ServiceFeeConfigRead(BaseModel):
    service_id: int
    freebie_enabled: bool
    freebie_default_days: int
    subscription_enabled: bool
    order_value_enabled: bool
    order_value_percent: float
    order_value_min_deposit: float
    order_value_billing_day: int
    pay_per_txn_enabled: bool
    pay_per_txn_fee: float
    pay_per_txn_min_deposit: float
    pay_per_txn_low_balance_threshold: float


class ServiceFeeConfigPatch(BaseModel):
    freebie_enabled: Optional[bool] = None
    freebie_default_days: Optional[int] = Field(default=None, ge=0, le=365)
    subscription_enabled: Optional[bool] = None
    order_value_enabled: Optional[bool] = None
    order_value_percent: Optional[float] = Field(default=None, ge=0, le=100)
    order_value_min_deposit: Optional[float] = Field(default=None, ge=0)
    order_value_billing_day: Optional[int] = Field(default=None, ge=1, le=28)
    pay_per_txn_enabled: Optional[bool] = None
    pay_per_txn_fee: Optional[float] = Field(default=None, ge=0)
    pay_per_txn_min_deposit: Optional[float] = Field(default=None, ge=0)
    pay_per_txn_low_balance_threshold: Optional[float] = Field(default=None, ge=0)


class SubscriptionPlanItem(BaseModel):
    duration_months: int
    price: float = Field(ge=0)
    is_active: bool = True


class SubscriptionPlansPut(BaseModel):
    plans: list[SubscriptionPlanItem]


class ServiceFeeConfigWithPlans(BaseModel):
    config: ServiceFeeConfigRead
    plans: list[SubscriptionPlanItem]


class SellerPaymentDetails(BaseModel):
    bank_account_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    upi_id: Optional[str] = None
    qr_image_url: Optional[str] = None
    gstin: Optional[str] = None


class SellerPlanServiceView(BaseModel):
    service_id: int
    service_name: str
    model: str
    status: str
    valid_until: Optional[str] = None
    subscription_enabled: bool
    subscription_plans: list[SubscriptionPlanItem] = []
    payment_pending: bool = False
    amount_due: Optional[float] = None
    cancel_requested: bool = False
    # Pay-Per-Transaction (prepaid) fields.
    pay_per_txn_enabled: bool = False
    pay_per_txn_fee: float = 0.0
    pay_per_txn_min_deposit: float = 0.0
    balance: Optional[float] = None
    low_balance_threshold: Optional[float] = None


class SellerPlanView(BaseModel):
    services: list[SellerPlanServiceView]
    payment_details: SellerPaymentDetails
    fee_credit_balance: float = 0.0


class OptInBody(BaseModel):
    duration_months: int  # 3, 6, or 12 (validated against active plans)


class PayPerTxnOptInBody(BaseModel):
    deposit_amount: float = Field(gt=0)
    use_credit: bool = False


class TopUpBody(BaseModel):
    amount: float = Field(gt=0)


class ApplyCreditBody(BaseModel):
    amount: float = Field(gt=0)


class AdminSwitchBody(BaseModel):
    target_model: str  # "subscription" | "freebie"
    duration_months: Optional[int] = None
    disposition: str = "credit"  # "credit" | "cash_out" | "waive"
    reason: str = Field(min_length=10, max_length=500)


class CreditAmountBody(BaseModel):
    """Shared body for admin credit grant/cash-out/waive (positive amount)."""
    amount: float = Field(gt=0)
    reason: str = Field(min_length=10, max_length=500)


class CreditAdjustBody(BaseModel):
    """Signed adjustment (may be negative)."""
    amount: float
    reason: str = Field(min_length=10, max_length=500)


class StoreCreditView(BaseModel):
    store_id: int
    store_name: str
    fee_credit_balance: float


class MarkPaidBody(BaseModel):
    seller_note: Optional[str] = Field(default=None, max_length=200)


class PaymentQueueItem(BaseModel):
    payment_id: int
    arrangement_id: int
    store_id: int
    store_name: str
    service_id: int
    service_name: str
    kind: str
    amount: float
    seller_note: Optional[str] = None
    pending_since: Optional[str] = None
    created_at: str


class RejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class ArrangementSummary(BaseModel):
    id: int
    service_id: int
    service_name: str
    model: str
    status: str
    valid_until: Optional[str] = None
    cancel_requested: bool = False
    pending: bool = False


class ExtendBody(BaseModel):
    days: int = Field(ge=1, le=3650)
    reason: Optional[str] = Field(default=None, max_length=500)


class TerminateBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CompBody(BaseModel):
    duration_months: int = Field(ge=1, le=60)
    reason: Optional[str] = Field(default=None, max_length=500)
