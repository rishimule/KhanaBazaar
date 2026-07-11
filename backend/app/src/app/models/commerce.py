# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import enum
from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import DateTime, Field, UniqueConstraint

from app.models.base import BaseSchema


class OrderStatus(str, enum.Enum):
    Pending = "pending"
    Paid = "paid"
    Packed = "packed"
    Dispatched = "dispatched"
    Delivered = "delivered"
    Cancelled = "cancelled"


class PaymentMethod(str, enum.Enum):
    Upi = "upi"
    Cash = "cash"
    Credit = "credit"
    NetBanking = "net_banking"
    PayAtStore = "pay_at_store"


class DeliveryMode(str, enum.Enum):
    DoorDelivery = "door_delivery"
    Pickup = "pickup"


class PaymentStatus(str, enum.Enum):
    Pending = "pending"
    Paid = "paid"
    Failed = "failed"
    Refunded = "refunded"


class DeliveryStatus(str, enum.Enum):
    Pending = "pending"
    Packed = "packed"
    Dispatched = "dispatched"
    Delivered = "delivered"
    Cancelled = "cancelled"


class Cart(BaseSchema, table=True):
    __table_args__ = (
        UniqueConstraint(
            "customer_profile_id", "store_id", "service_id",
            name="uq_cart_customer_store_service",
        ),
    )
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False)
    store_id: int = Field(foreign_key="store.id", nullable=False)
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)


class CartItem(BaseSchema, table=True):
    __tablename__ = "cartitem"
    __table_args__ = (UniqueConstraint("cart_id", "inventory_id", name="uq_cartitem_cart_inventory"),)
    cart_id: int = Field(foreign_key="cart.id", nullable=False)
    inventory_id: int = Field(foreign_key="storeinventory.id", nullable=False)
    quantity: int = Field(nullable=False)


class Order(BaseSchema, table=True):
    __tablename__ = "order"
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False, index=True)
    store_id: int = Field(foreign_key="store.id", nullable=False, index=True)
    service_id: int = Field(foreign_key="service.id", nullable=False, index=True)
    service_name_snapshot: str = Field(nullable=False)
    delivery_eta_min_minutes: int = Field(default=30, nullable=False)
    delivery_eta_max_minutes: int = Field(default=60, nullable=False)
    preferred_delivery_date: Optional[date] = Field(default=None, nullable=True)
    preferred_delivery_window: Optional[str] = Field(
        default=None, max_length=16, nullable=True
    )
    delivery_address_id: int = Field(foreign_key="address.id", nullable=False)
    delivery_mode: DeliveryMode = Field(
        default=DeliveryMode.DoorDelivery, nullable=False
    )
    status: OrderStatus = Field(default=OrderStatus.Pending, nullable=False, index=True)
    subtotal: float = Field(nullable=False)
    delivery_fee: float = Field(nullable=False)
    tax: float = Field(nullable=False)
    total: float = Field(nullable=False)
    delivery_address_snapshot: str = Field(nullable=False)
    placed_at: datetime = Field(  # type: ignore[call-overload]
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class OrderItem(BaseSchema, table=True):
    __tablename__ = "orderitem"
    __table_args__ = (UniqueConstraint("order_id", "inventory_id", name="uq_orderitem_order_inventory"),)
    order_id: int = Field(foreign_key="order.id", nullable=False)
    inventory_id: Optional[int] = Field(default=None, foreign_key="storeinventory.id")
    product_name_snapshot: str = Field(nullable=False)
    unit_price_snapshot: float = Field(nullable=False)
    quantity: int = Field(nullable=False)
    line_total: float = Field(nullable=False)


class Payment(BaseSchema, table=True):
    order_id: int = Field(foreign_key="order.id", nullable=False, index=True)
    amount: float = Field(nullable=False)
    method: PaymentMethod = Field(default=PaymentMethod.Upi, nullable=False)
    status: PaymentStatus = Field(default=PaymentStatus.Pending, nullable=False)
    gateway_txn_id: Optional[str] = Field(default=None, unique=True, index=True)
    paid_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None,
        sa_type=DateTime(timezone=True),
    )


class Delivery(BaseSchema, table=True):
    order_id: int = Field(foreign_key="order.id", nullable=False, unique=True, index=True)
    status: DeliveryStatus = Field(default=DeliveryStatus.Pending, nullable=False)
    packed_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None,
        sa_type=DateTime(timezone=True),
    )
    dispatched_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None,
        sa_type=DateTime(timezone=True),
    )
    delivered_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None,
        sa_type=DateTime(timezone=True),
    )
    tracking_notes: Optional[str] = Field(default=None)
    delivery_otp: Optional[str] = Field(default=None, max_length=6)
    delivery_otp_attempts: int = Field(default=0, nullable=False)
    delivery_otp_sent_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None,
        sa_type=DateTime(timezone=True),
    )
    delivery_otp_verified_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None,
        sa_type=DateTime(timezone=True),
    )


class Review(BaseSchema, table=True):
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False, index=True)
    product_id: Optional[int] = Field(default=None, foreign_key="masterproduct.id", index=True)
    store_id: Optional[int] = Field(default=None, foreign_key="store.id", index=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    rating: int = Field(nullable=False)
    comment: Optional[str] = Field(default=None)


class Favorite(BaseSchema, table=True):
    __table_args__ = (UniqueConstraint("customer_profile_id", "product_id", name="uq_favorite_customer_product"),)
    customer_profile_id: int = Field(foreign_key="customerprofile.id", nullable=False)
    product_id: int = Field(foreign_key="masterproduct.id", nullable=False)
