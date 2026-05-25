# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NotificationRead(BaseModel):
    id: int
    order_id: Optional[int]
    type: str
    title: str
    body: str
    status_value: str
    read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: List[NotificationRead]
    unread_count: int


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1)
    keys: PushSubscriptionKeys
    user_agent: Optional[str] = None


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1)
