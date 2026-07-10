# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add credit tables

Revision ID: f6495e1b1c31
Revises: 0f6d3ef363f0
Create Date: 2026-07-09 21:15:42.677624

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f6495e1b1c31'
down_revision: Union[str, Sequence[str], None] = '0f6d3ef363f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

account_status = postgresql.ENUM(
    "active", "suspended", name="creditaccountstatus", create_type=False
)
entry_type = postgresql.ENUM(
    "charge", "repayment", "reversal", name="creditentrytype", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    account_status.create(bind, checkfirst=True)
    entry_type.create(bind, checkfirst=True)
    # Native enums store member NAMES; add the PascalCase 'Credit'. IF NOT EXISTS
    # makes it idempotent; PG15 allows ADD VALUE inside the tx since no column
    # in this migration uses the new value.
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'Credit'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'Credit'")

    op.create_table(
        "seller_credit_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "seller_profile_id",
            sa.Integer(),
            sa.ForeignKey("sellerprofile.id"),
            nullable=False,
        ),
        sa.Column(
            "credit_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "max_limit_per_customer",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_seller_credit_config_seller_profile_id",
        "seller_credit_config",
        ["seller_profile_id"],
    )
    op.create_unique_constraint(
        "uq_seller_credit_config_seller", "seller_credit_config", ["seller_profile_id"]
    )

    op.create_table(
        "credit_account",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "seller_profile_id",
            sa.Integer(),
            sa.ForeignKey("sellerprofile.id"),
            nullable=False,
        ),
        sa.Column(
            "customer_profile_id",
            sa.Integer(),
            sa.ForeignKey("customerprofile.id"),
            nullable=False,
        ),
        sa.Column("credit_limit", sa.Float(), nullable=False),
        sa.Column(
            "outstanding_balance",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("status", account_status, nullable=False, server_default="active"),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "last_notified_threshold",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_credit_account_seller_profile_id", "credit_account", ["seller_profile_id"]
    )
    op.create_index(
        "ix_credit_account_customer", "credit_account", ["customer_profile_id"]
    )
    op.create_unique_constraint(
        "uq_credit_account_pair",
        "credit_account",
        ["seller_profile_id", "customer_profile_id"],
    )

    op.create_table(
        "credit_ledger_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "credit_account_id",
            sa.Integer(),
            sa.ForeignKey("credit_account.id"),
            nullable=False,
        ),
        sa.Column("entry_type", entry_type, nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=True),
        sa.Column("balance_after", sa.Float(), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_credit_ledger_entry_credit_account_id",
        "credit_ledger_entry",
        ["credit_account_id"],
    )
    op.create_index(
        "ix_credit_ledger_account_created",
        "credit_ledger_entry",
        ["credit_account_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("credit_ledger_entry")
    op.drop_table("credit_account")
    op.drop_table("seller_credit_config")
    entry_type.drop(op.get_bind(), checkfirst=True)
    account_status.drop(op.get_bind(), checkfirst=True)
    # paymentmethod / notificationtype enum values intentionally left in place
    # (PostgreSQL cannot drop enum values).
