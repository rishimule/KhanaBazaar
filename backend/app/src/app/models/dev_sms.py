# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Dev-only capture of outbound SMS (see core/dev_mailbox.py)."""
from typing import Optional

from sqlmodel import Field

from app.models.base import BaseSchema


class DevSms(BaseSchema, table=True):
    __tablename__ = "dev_sms"

    to_phone: str = Field(index=True)
    body: str
    category: Optional[str] = Field(default=None, index=True)
    provider: str = Field(default="console")
