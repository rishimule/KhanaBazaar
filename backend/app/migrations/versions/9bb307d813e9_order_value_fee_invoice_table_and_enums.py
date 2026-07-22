# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""order value fee invoice table and enums

Adds the Order Value % (postpaid + security deposit) fee-model schema:
- invoicestatus enum + fee_invoice table (monthly postpaid charges)
- service_fee_config.order_value_payment_days (net days before an invoice is due)
- fee_arrangement.order_value_activated_on + last_billed_period_end (billing anchors)
- notificationtype += FeeInvoiceRaised, FeeInvoiceOverdue (enum stores NAMES)

No feeeventtype change — InvoiceIssued/InvoicePaid/InvoiceWaived/DepositForfeited/
DepositRefunded/Activated/Reactivated/Suspended already exist.

Revision ID: 9bb307d813e9
Revises: f6568edb5ae5
Create Date: 2026-07-22 00:34:36.011776

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9bb307d813e9"
down_revision: Union[str, Sequence[str], None] = "f6568edb5ae5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# postgresql.ENUM(create_type=False) + explicit pre-create — mirrors 343d1ef4da58 /
# f6568edb5ae5. Labels are the lowercase member VALUES (invoicestatus uses
# values_callable in the model).
invoice_status = postgresql.ENUM(
    "pending", "paid", "overdue", "waived", "cancelled",
    name="invoicestatus", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    invoice_status.create(bind, checkfirst=True)

    # --- new config + arrangement columns (existing rows need a default) ---
    op.add_column(
        "service_fee_config",
        sa.Column(
            "order_value_payment_days", sa.Integer(), nullable=False, server_default="7"
        ),
    )
    op.alter_column("service_fee_config", "order_value_payment_days", server_default=None)

    op.add_column(
        "fee_arrangement", sa.Column("order_value_activated_on", sa.Date(), nullable=True)
    )
    op.add_column(
        "fee_arrangement", sa.Column("last_billed_period_end", sa.Date(), nullable=True)
    )

    # --- fee_invoice table (BaseSchema: id/created_at/updated_at) ---
    op.create_table(
        "fee_invoice",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrangement_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("sales_total", sa.Float(), nullable=False),
        sa.Column("fee_percent_snapshot", sa.Float(), nullable=False),
        sa.Column("amount_due", sa.Float(), nullable=False),
        sa.Column("status", invoice_status, nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("suspend_after", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["arrangement_id"], ["fee_arrangement.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["fee_payment.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "arrangement_id", "period_start", name="uq_fee_invoice_arrangement_period"
        ),
    )
    op.create_index(
        op.f("ix_fee_invoice_arrangement_id"), "fee_invoice", ["arrangement_id"]
    )
    op.create_index(op.f("ix_fee_invoice_store_id"), "fee_invoice", ["store_id"])
    op.create_index(op.f("ix_fee_invoice_service_id"), "fee_invoice", ["service_id"])
    op.create_index(op.f("ix_fee_invoice_status"), "fee_invoice", ["status"])

    # NotificationType stores NAMES; add the two new members (tx-safe on PG15,
    # precedent: f6568edb5ae5 FeeLowBalance/FeeReactivated).
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'FeeInvoiceRaised'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'FeeInvoiceOverdue'")


def downgrade() -> None:
    op.drop_index(op.f("ix_fee_invoice_status"), table_name="fee_invoice")
    op.drop_index(op.f("ix_fee_invoice_service_id"), table_name="fee_invoice")
    op.drop_index(op.f("ix_fee_invoice_store_id"), table_name="fee_invoice")
    op.drop_index(op.f("ix_fee_invoice_arrangement_id"), table_name="fee_invoice")
    op.drop_table("fee_invoice")
    invoice_status.drop(op.get_bind(), checkfirst=True)
    op.drop_column("fee_arrangement", "last_billed_period_end")
    op.drop_column("fee_arrangement", "order_value_activated_on")
    op.drop_column("service_fee_config", "order_value_payment_days")
    # notificationtype VALUEs are not removed (PG cannot DROP an enum value).
