# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from datetime import datetime

from pydantic import BaseModel


class OrderSummary(BaseModel):
    id: int
    store_id: int
    store_name: str
    service_id: int
    service_name: str
    total: float
    placed_at: datetime


class CustomerStatsResponse(BaseModel):
    orders_this_month: int
    lifetime_spend: float
    most_ordered_store_id: int | None
    most_ordered_store_name: str | None
    recent_delivered: list[OrderSummary]
