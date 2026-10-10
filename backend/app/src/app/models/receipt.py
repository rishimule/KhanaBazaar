# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Order receipts (spec 2026-10-10-order-receipts-design.md §2).

One frozen receipt per delivered order. `snapshot` holds everything the
receipt prints (schemas.receipts.ReceiptSnapshotV1), so a later profile edit
never changes an issued receipt. Numbers run per store per Indian financial
year from `order_receipt_counter`; services/receipts.py is the only writer.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import DateTime, Field, SQLModel, UniqueConstraint

from app.models.base import BaseSchema


class OrderReceipt(BaseSchema, table=True):
    __tablename__ = "order_receipt"
    __table_args__ = (
        UniqueConstraint("store_id", "fiscal_year", "seq", name="uq_order_receipt_store_fy_seq"),
    )
    order_id: int = Field(foreign_key="order.id", nullable=False, unique=True, index=True)
    store_id: int = Field(foreign_key="store.id", nullable=False, index=True)
    # Start year of the Indian financial year: FY 2026-27 is 2026.
    fiscal_year: int = Field(nullable=False)
    seq: int = Field(nullable=False)
    number: str = Field(nullable=False, max_length=16)
    issued_at: datetime = Field(  # type: ignore[call-overload]
        nullable=False, sa_type=DateTime(timezone=True)
    )
    # "delivery" (issued live) | "backfill" (built later from order records).
    issued_via: str = Field(nullable=False, max_length=16)
    snapshot_version: int = Field(default=1, nullable=False)
    snapshot: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )


class OrderReceiptCounter(SQLModel, table=True):
    """Last number used per store per financial year. Bumped only by the
    upsert in services/receipts._next_seq, inside the delivery transaction."""

    __tablename__ = "order_receipt_counter"
    store_id: int = Field(foreign_key="store.id", primary_key=True)
    fiscal_year: int = Field(primary_key=True)
    last_seq: int = Field(nullable=False)
