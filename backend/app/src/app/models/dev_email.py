# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Dev-only capture of outbound emails (see core/dev_mailbox.py)."""
from typing import Optional

from sqlmodel import Field

from app.models.base import BaseSchema


class DevEmail(BaseSchema, table=True):
    __tablename__ = "dev_email"

    to_email: str = Field(index=True)
    subject: str
    body_text: str
    body_html: Optional[str] = Field(default=None)
    reply_to: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None, index=True)
    provider: str = Field(default="console")
