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
