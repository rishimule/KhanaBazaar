# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.price_comparison import ReplaceAdjustment


class ResolvedReorderItem(BaseModel):
    product_id: int
    inventory_id: int
    product_name: str
    image_url: Optional[str] = None
    unit_price: float
    quantity: int


class ReorderResolveResponse(BaseModel):
    store_id: int
    store_name: str
    service_id: int
    service_name: str
    items: List[ResolvedReorderItem]
    adjustments: List[ReplaceAdjustment]
