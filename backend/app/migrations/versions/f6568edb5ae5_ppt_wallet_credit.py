# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""ppt wallet credit

Adds the Pay-Per-Transaction wallet-credit scaffolding:
- store.fee_credit_balance (cached store wallet-credit balance)
- fee_event.order_id (links balance deduct/refund events to their order)
- store_credit_event ledger + storecreditreason enum
- notificationtype += FeeLowBalance, FeeReactivated (enum stores NAMES)

Revision ID: f6568edb5ae5
Revises: 9b5b0cf69335
Create Date: 2026-07-21 16:39:29.558592

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f6568edb5ae5'
down_revision: Union[str, Sequence[str], None] = '9b5b0cf69335'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# postgresql.ENUM(create_type=False) + explicit pre-create — mirrors the
# platform-fee migration 343d1ef4da58. Values are the lowercase member VALUES.
store_credit_reason = postgresql.ENUM(
    "granted_on_exit", "applied_to_fee", "admin_cash_out", "admin_adjust",
    name="storecreditreason", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    store_credit_reason.create(bind, checkfirst=True)

    op.add_column(
        "store",
        sa.Column("fee_credit_balance", sa.Float(), nullable=False, server_default="0"),
    )
    op.alter_column("store", "fee_credit_balance", server_default=None)

    op.add_column("fee_event", sa.Column("order_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_fee_event_order_id"), "fee_event", ["order_id"])
    op.create_foreign_key(
        "fk_fee_event_order", "fee_event", "order", ["order_id"], ["id"]
    )

    op.create_table(
        "store_credit_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("amount_delta", sa.Float(), nullable=False),
        sa.Column("reason", store_credit_reason, nullable=False),
        sa.Column("related_arrangement_id", sa.Integer(), nullable=True),
        sa.Column("related_payment_id", sa.Integer(), nullable=True),
        sa.Column("actor", sqlmodel.sql.sqltypes.AutoString(length=60), nullable=True),
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.ForeignKeyConstraint(["related_arrangement_id"], ["fee_arrangement.id"]),
        sa.ForeignKeyConstraint(["related_payment_id"], ["fee_payment.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_store_credit_event_store_id"), "store_credit_event", ["store_id"]
    )

    # NotificationType stores NAMES; add the two new members (tx-safe on PG15,
    # precedent: 1a82f642a321 DeliveryOtp + 662ea92dac16 fee names).
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'FeeLowBalance'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'FeeReactivated'")


def downgrade() -> None:
    op.drop_index(op.f("ix_store_credit_event_store_id"), table_name="store_credit_event")
    op.drop_table("store_credit_event")
    store_credit_reason.drop(op.get_bind(), checkfirst=True)
    op.drop_constraint("fk_fee_event_order", "fee_event", type_="foreignkey")
    op.drop_index(op.f("ix_fee_event_order_id"), table_name="fee_event")
    op.drop_column("fee_event", "order_id")
    op.drop_column("store", "fee_credit_balance")
    # notificationtype VALUEs are not removed (PG cannot DROP an enum value).
