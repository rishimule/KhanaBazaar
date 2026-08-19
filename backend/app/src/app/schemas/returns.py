# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from pydantic import Field as PydanticField

from app.models.returns import (
    ReturnInitiator,
    ReturnReasonCode,
    ReturnSettlementChoice,
    ReturnStatus,
)


class ReturnEligibilityLine(BaseModel):
    order_item_id: int
    product_name: str
    unit_price: float
    quantity: int
    line_total: float
    returnable: bool
    lock_reason: Optional[str] = None


class ReturnEligibilityRead(BaseModel):
    order_id: int
    eligible: bool
    reason_code: Optional[str] = None
    window_expires_at: Optional[datetime] = None
    delivery_fee: float
    full_order_available: bool
    agreement_version: Optional[int] = None
    lines: list[ReturnEligibilityLine]


class ReturnItemRead(BaseModel):
    order_item_id: int
    product_name: str
    unit_price: float
    quantity: int
    line_total: float


class ReturnRead(BaseModel):
    id: int
    order_id: int
    store_id: int
    seller_profile_id: int
    status: ReturnStatus
    initiated_by: ReturnInitiator
    is_full_order: bool
    reason_code: ReturnReasonCode
    reason_note: Optional[str] = None
    items_amount: float
    delivery_fee_amount: float
    total_amount: float
    settlement_choice: ReturnSettlementChoice
    credit_reversal_amount: float
    store_credit_amount: float
    payment_amount: float
    rejection_reason: Optional[str] = None
    agreement_policy_version: int
    window_expires_at: datetime
    confirm_expires_at: datetime
    handover_expires_at: Optional[datetime] = None
    created_at: datetime
    items: list[ReturnItemRead] = []
    # Present only for the owning customer while the return is `active`.
    # Sellers never receive it — they type what the customer shows them.
    receipt_otp: Optional[str] = None


class ReturnCreateBody(BaseModel):
    order_id: int
    order_item_ids: list[int] = PydanticField(min_length=1)
    reason_code: ReturnReasonCode
    reason_note: Optional[str] = PydanticField(default=None, max_length=500)
    settlement_choice: ReturnSettlementChoice


class ReturnCreateOnBehalfBody(ReturnCreateBody):
    """Seller/admin initiating for a customer. The customer's consent OTP is
    still required before the return becomes active."""

    customer_profile_id: int


class ReturnConfirmBody(BaseModel):
    otp: str = PydanticField(min_length=4, max_length=8)
    agreement_accepted: bool


class ReturnAcceptBody(BaseModel):
    otp: Optional[str] = PydanticField(default=None, max_length=16)
    restock: bool = False


class ReturnRejectBody(BaseModel):
    reason: str = PydanticField(max_length=500)


class ReturnPaymentConfirmBody(BaseModel):
    otp: str = PydanticField(min_length=4, max_length=8)


class StoreCreditBalanceRead(BaseModel):
    seller_profile_id: int
    # The checkout page knows the store, not the seller. Matching on the
    # display name instead was fragile: a rename or a duplicate name silently
    # applied the wrong seller's credit.
    store_id: Optional[int] = None
    store_name: str
    balance: float
    lifetime_earned: float
    lifetime_spent: float


class StoreCreditEntryRead(BaseModel):
    id: int
    entry_type: str
    amount: float
    balance_after: float
    return_request_id: Optional[int] = None
    order_id: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime


class AdminReturnAcceptBody(BaseModel):
    """`reason` length is checked in the handler, not here, so the error comes
    back in the repo's `{"code": ...}` shape rather than Pydantic's."""

    reason: str = PydanticField(max_length=500)
    restock: bool = False


class AdminReturnReasonBody(BaseModel):
    reason: str = PydanticField(max_length=500)
