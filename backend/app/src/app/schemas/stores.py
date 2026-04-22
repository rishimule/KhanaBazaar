"""Wire-format models for store endpoints."""

from pydantic import BaseModel

from app.schemas.address import AddressPayload


class StoreCreate(BaseModel):
    name: str
    address: AddressPayload


class StoreRead(BaseModel):
    id: int
    name: str
    address: AddressPayload
    is_active: bool
    seller_id: int
    created_at: str
    updated_at: str
