"""Wire-format models for store endpoints."""

from pydantic import BaseModel

from app.schemas.address import AddressPayload
from app.schemas.services import ServicePayload


class StoreCreate(BaseModel):
    name: str
    address: AddressPayload


class StoreRead(BaseModel):
    id: int
    name: str
    address: AddressPayload
    is_active: bool
    seller_id: int
    services: list[ServicePayload] = []
    created_at: str
    updated_at: str
