# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Dev-only capture of outbound WhatsApp messages (see core/dev_mailbox.py)."""
from typing import Optional

from sqlmodel import Field

from app.models.base import BaseSchema


class DevWhatsApp(BaseSchema, table=True):
    __tablename__ = "dev_whatsapp"

    to_phone: str = Field(index=True)
    body: str
    template: Optional[str] = Field(default=None, index=True)
    category: Optional[str] = Field(default=None, index=True)
    provider: str = Field(default="console")
