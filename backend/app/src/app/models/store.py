# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import date

from sqlmodel import Field, Relationship, UniqueConstraint

from app.models.address import Address
from app.models.base import BaseSchema
from app.models.catalog import MasterProduct
from app.models.profile import SellerProfile


class Store(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("seller_profile_id", name="uq_store_seller_profile"),)
    name: str = Field(index=True, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    seller_profile_id: int = Field(foreign_key="sellerprofile.id", nullable=False, index=True)
    address_id: int = Field(foreign_key="address.id", nullable=False, index=True)
    delivery_radius_km: float = Field(default=5.0, nullable=False)
    pin_confirmed: bool = Field(default=False, nullable=False)
    is_paused: bool = Field(default=False, nullable=False)
    pause_reason: str | None = Field(default=None, max_length=200)
    paused_until: date | None = Field(default=None)
    logo_url: str | None = Field(default=None, max_length=2048)
    logo_storage_key: str | None = Field(default=None, max_length=512)
    fee_credit_balance: float = Field(default=0.0, nullable=False)

    seller_profile: SellerProfile = Relationship()
    address: Address = Relationship()


class StoreInventory(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("store_id", "product_id", name="uq_store_product"),)
    store_id: int = Field(foreign_key="store.id", nullable=False)
    product_id: int = Field(foreign_key="masterproduct.id", nullable=False)
    price: float = Field(nullable=False)
    stock: int = Field(default=0, nullable=False)
    is_available: bool = Field(default=True, nullable=False)

    store: Store = Relationship()
    product: MasterProduct = Relationship()
