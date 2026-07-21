# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime

from pydantic import BaseModel, Field


class AdminCustomerActionBody(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class AdminCustomerListItem(BaseModel):
    customer_profile_id: int
    user_id: int
    email: str
    full_name: str | None
    phone: str | None
    account_status: str
    created_at: datetime


class AdminCustomerList(BaseModel):
    items: list[AdminCustomerListItem]
    total: int


class AdminCustomerHub(BaseModel):
    customer_profile_id: int
    user_id: int
    email: str
    full_name: str | None
    phone: str | None
    account_status: str
    status_reason: str | None
    status_changed_at: datetime | None
    open_orders: int
    open_credit_accounts: int


class AdminCustomerEvent(BaseModel):
    id: int
    actor_user_id: int | None
    actor_role: str
    from_status: str
    to_status: str
    reason: str | None
    created_at: datetime


class AdminCustomerOrder(BaseModel):
    id: int
    store_id: int
    service_name_snapshot: str
    status: str
    total: float
    placed_at: datetime


class AdminCustomerNotification(BaseModel):
    id: int
    type: str
    title: str
    body: str
    read: bool
    created_at: datetime
