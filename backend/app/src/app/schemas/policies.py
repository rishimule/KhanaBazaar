# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PolicyDocumentRead(BaseModel):
    kind: str
    version: int
    body: str
    published_at: datetime


class PolicyStatusRead(BaseModel):
    required: bool
    version: Optional[str] = None


class PolicyPublishBody(BaseModel):
    body: str = Field(min_length=1, max_length=200_000)


class PolicyAdminItem(BaseModel):
    kind: str
    version: int
    body: str
    published_at: Optional[datetime] = None


class PolicyHistoryItem(BaseModel):
    version: int
    published_at: datetime
    published_by: Optional[int] = None
