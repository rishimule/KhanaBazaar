# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""courier delivery

Revision ID: 4675f7be7055
Revises: 68770edd47ff
Create Date: 2026-10-03 12:22:44.052061

Long-distance courier orders (spec 2026-10-02). A store can ship beyond its
local radius, up to `store.courier_radius_km`, for the services it switches
on (`sellerprofile_service.courier_enabled`). The seller quotes the courier
charge after the order is placed (`courier_quote`, append-only), and the
per-order courier state lives in `order_courier`.

The enum values are only added here, never used: Postgres refuses to use an
enum value inside the transaction that created it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4675f7be7055'
down_revision: Union[str, Sequence[str], None] = '68770edd47ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Native PG enums store the member NAME (schema.sql header). None of the new
    # values is *used* in this migration — Postgres rejects using an enum value
    # inside the transaction that added it.
    op.execute("ALTER TYPE deliverymode ADD VALUE IF NOT EXISTS 'Courier'")
    op.execute("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'Quoted'")
    op.execute("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'Accepted'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'SellerOrderUpdate'")

    op.add_column("store", sa.Column("courier_radius_km", sa.Float(), nullable=True))
    op.add_column(
        "sellerprofile_service",
        sa.Column("courier_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("sellerprofile", sa.Column("bank_account_name", sa.String(length=140), nullable=True))
    op.add_column(
        "sellerprofile",
        sa.Column("bank_transfer_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("payment", sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payment", sa.Column("refund_reference", sa.String(length=60), nullable=True))
    op.add_column(
        "payment",
        sa.Column("refunded_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
    )

    op.create_table(
        "courier_quote",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("courier_fee", sa.Float(), nullable=False),
        sa.Column("eta_min_days", sa.Integer(), nullable=False),
        sa.Column("eta_max_days", sa.Integer(), nullable=False),
        sa.Column("carrier_name", sa.String(length=80), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.UniqueConstraint("order_id", "version", name="uq_courier_quote_order_version"),
    )
    op.create_index("ix_courier_quote_order_id", "courier_quote", ["order_id"])

    op.create_table(
        "order_courier",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=False),
        sa.Column("recipient_name", sa.String(length=120), nullable=False),
        sa.Column("recipient_phone", sa.String(length=20), nullable=False),
        sa.Column("apply_store_credit", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("accepted_quote_id", sa.Integer(), sa.ForeignKey("courier_quote.id"), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eta_from", sa.Date(), nullable=True),
        sa.Column("eta_to", sa.Date(), nullable=True),
        sa.Column("payment_claim_rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_claim_rejected_note", sa.String(length=300), nullable=True),
        sa.Column("payment_claim_rejection_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("carrier_name", sa.String(length=80), nullable=True),
        sa.Column("tracking_number", sa.String(length=60), nullable=True),
        sa.Column("tracking_url", sa.String(length=500), nullable=True),
        sa.Column("tracking_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_by", sa.String(length=16), nullable=True),
        sa.Column("cancel_reason", sa.String(length=300), nullable=True),
        sa.Column("cancelled_by", sa.String(length=16), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_reported_missing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reminder_key", sa.String(length=40), nullable=True),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_order_courier_order_id", "order_courier", ["order_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_order_courier_order_id", table_name="order_courier")
    op.drop_table("order_courier")
    op.drop_index("ix_courier_quote_order_id", table_name="courier_quote")
    op.drop_table("courier_quote")
    op.drop_column("payment", "refunded_by_user_id")
    op.drop_column("payment", "refund_reference")
    op.drop_column("payment", "refunded_at")
    op.drop_column("sellerprofile", "bank_transfer_enabled")
    op.drop_column("sellerprofile", "bank_account_name")
    op.drop_column("sellerprofile_service", "courier_enabled")
    op.drop_column("store", "courier_radius_km")
    # NOTE: PostgreSQL cannot drop individual enum values; 'Courier',
    # 'Quoted', 'Accepted' and 'SellerOrderUpdate' remain on downgrade.
