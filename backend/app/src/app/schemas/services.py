"""Wire-format model for services. Mirrors the shape returned by
GET /catalog/services so frontend code can reuse a single Service type."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ServicePayload(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    slug: str
    name: str
    description: Optional[str] = None
    is_active: bool
    sort_order: int
