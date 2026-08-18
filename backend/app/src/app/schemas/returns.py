# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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
