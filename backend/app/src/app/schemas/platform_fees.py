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
