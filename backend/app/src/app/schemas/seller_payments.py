# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Wire models for the seller payment settings (spec 2026-10-07 §4, §8)."""
from typing import Optional

from pydantic import BaseModel, Field

from app.models.commerce import PaymentMethod


class PaymentSettingsRead(BaseModel):
    upi_enabled: bool
    upi_vpa: Optional[str] = None
    upi_live: bool
    bank_transfer_enabled: bool
    bank_account_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_details_complete: bool
    bank_transfer_live: bool
    cod_enabled: bool
    pay_at_store_enabled: bool
    pickup_offered: bool
    courier_offered: bool
    # What customers see at checkout: door delivery always; pickup and courier
    # only while the store offers them. An empty list = no way to pay.
    methods_by_mode: dict[str, list[PaymentMethod]]


class PaymentMethodsUpdate(BaseModel):
    """Omitted = unchanged."""

    upi_enabled: Optional[bool] = None
    bank_transfer_enabled: Optional[bool] = None
    cod_enabled: Optional[bool] = None
    pay_at_store_enabled: Optional[bool] = None


class AdminPaymentMethodsUpdate(PaymentMethodsUpdate):
    # Checked for ≥ 10 characters after trimming, like other admin actions.
    reason: Optional[str] = Field(default=None, max_length=500)
