# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""order receipts

Revision ID: 5e1c9a7b3d20
Revises: 378bcb4c2c06
Create Date: 2026-10-10 10:00:00.000000

Order receipts (spec 2026-10-10). One frozen receipt per delivered order,
numbered per store per Indian financial year from `order_receipt_counter`.
Tables only: the historical backfill is scripts/backfill_order_receipts.py,
which deploy_release.sh runs right after this migration and before the new
API goes live, so history is numbered ahead of any live receipt.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5e1c9a7b3d20"
down_revision: Union[str, Sequence[str], None] = "378bcb4c2c06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_receipt_counter",
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("store.id"), primary_key=True),
        sa.Column("fiscal_year", sa.Integer(), primary_key=True),
        sa.Column("last_seq", sa.Integer(), nullable=False),
    )
    op.create_table(
        "order_receipt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("store.id"), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_via", sa.String(length=16), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "store_id", "fiscal_year", "seq", name="uq_order_receipt_store_fy_seq"
        ),
    )
    op.create_index("ix_order_receipt_order_id", "order_receipt", ["order_id"], unique=True)
    op.create_index("ix_order_receipt_store_id", "order_receipt", ["store_id"])


def downgrade() -> None:
    op.drop_index("ix_order_receipt_store_id", table_name="order_receipt")
    op.drop_index("ix_order_receipt_order_id", table_name="order_receipt")
    op.drop_table("order_receipt")
    op.drop_table("order_receipt_counter")
