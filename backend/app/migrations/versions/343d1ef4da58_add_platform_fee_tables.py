# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add platform fee tables

Revision ID: 343d1ef4da58
Revises: 01deacebe263
Create Date: 2026-07-05 08:40:24.854956

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "343d1ef4da58"
down_revision: Union[str, Sequence[str], None] = "01deacebe263"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Use postgresql.ENUM (NOT generic sa.Enum): create_type=False is only honored
# on the PG dialect ENUM. With a generic sa.Enum, Alembic's create_table
# re-issues CREATE TYPE (it dispatches before_create with checkfirst hardcoded
# False), colliding with the pre-create loop below → DuplicateObjectError. This
# mirrors the working migration 4e5739351677. Each enum is used by exactly one
# table; feemodel backs two columns of fee_arrangement via this one shared object
# (one CREATE TYPE). Values are the lowercase snake_case member VALUES.
fee_model = postgresql.ENUM(
    "freebie", "subscription", "order_value_percent", "pay_per_transaction",
    name="feemodel", create_type=False,
)
arrangement_status = postgresql.ENUM(
    "trial", "pending_activation", "active", "grace", "suspended",
    name="arrangementstatus", create_type=False,
)
fee_payment_kind = postgresql.ENUM(
    "subscription_fee", "security_deposit", "pay_per_txn_topup", "order_value_invoice",
    name="feepaymentkind", create_type=False,
)
fee_payment_status = postgresql.ENUM(
    "pending", "confirmed", "rejected", name="feepaymentstatus", create_type=False,
)
fee_event_type = postgresql.ENUM(
    "arrangement_created", "model_changed", "activated", "extended", "renewed",
    "trial_held", "reminder_sent", "grace_started", "suspended", "reactivated",
    "terminated", "payment_recorded", "payment_confirmed", "payment_rejected",
    "deposit_recorded", "deposit_forfeited", "deposit_refunded", "balance_topup",
    "balance_deducted", "balance_refunded", "invoice_issued", "invoice_paid",
    "invoice_waived",
    name="feeeventtype", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for e in (fee_model, arrangement_status, fee_payment_kind, fee_payment_status, fee_event_type):
        e.create(bind, checkfirst=True)

    op.create_table(
        "platform_fee_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grace_period_days", sa.Integer(), nullable=False),
        sa.Column("expiry_reminder_start_days", sa.Integer(), nullable=False),
        sa.Column("pending_payment_protect_days", sa.Integer(), nullable=False),
        sa.Column("bank_account_name", sqlmodel.sql.sqltypes.AutoString(length=140), nullable=True),
        sa.Column("bank_account_number", sqlmodel.sql.sqltypes.AutoString(length=40), nullable=True),
        sa.Column("bank_ifsc", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column("upi_id", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column("qr_image_url", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("qr_storage_key", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.Column("gstin", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "service_fee_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("freebie_enabled", sa.Boolean(), nullable=False),
        sa.Column("freebie_default_days", sa.Integer(), nullable=False),
        sa.Column("subscription_enabled", sa.Boolean(), nullable=False),
        sa.Column("order_value_enabled", sa.Boolean(), nullable=False),
        sa.Column("order_value_percent", sa.Float(), nullable=False),
        sa.Column("order_value_min_deposit", sa.Float(), nullable=False),
        sa.Column("order_value_billing_day", sa.Integer(), nullable=False),
        sa.Column("pay_per_txn_enabled", sa.Boolean(), nullable=False),
        sa.Column("pay_per_txn_fee", sa.Float(), nullable=False),
        sa.Column("pay_per_txn_min_deposit", sa.Float(), nullable=False),
        sa.Column("pay_per_txn_low_balance_threshold", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", name="uq_service_fee_config_service"),
    )
    op.create_index(op.f("ix_service_fee_config_service_id"), "service_fee_config", ["service_id"])

    op.create_table(
        "service_subscription_plan",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "duration_months", name="uq_service_subscription_plan"),
    )
    op.create_index(op.f("ix_service_subscription_plan_service_id"), "service_subscription_plan", ["service_id"])

    op.create_table(
        "fee_arrangement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("model", fee_model, nullable=False),
        sa.Column("status", arrangement_status, nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("subscription_duration_months", sa.Integer(), nullable=True),
        sa.Column("price_snapshot", sa.Float(), nullable=True),
        sa.Column("security_deposit_amount", sa.Float(), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False),
        sa.Column("auto_renew", sa.Boolean(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("queued_model", fee_model, nullable=True),
        sa.Column("queued_duration_months", sa.Integer(), nullable=True),
        sa.Column("queued_effective_date", sa.Date(), nullable=True),
        sa.Column("pending_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reminder_sent_on", sa.Date(), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_reason", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "service_id", name="uq_fee_arrangement_store_service"),
    )
    op.create_index(op.f("ix_fee_arrangement_store_id"), "fee_arrangement", ["store_id"])
    op.create_index(op.f("ix_fee_arrangement_service_id"), "fee_arrangement", ["service_id"])
    op.create_index(op.f("ix_fee_arrangement_status"), "fee_arrangement", ["status"])

    op.create_table(
        "fee_payment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrangement_id", sa.Integer(), nullable=False),
        sa.Column("kind", fee_payment_kind, nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("status", fee_payment_status, nullable=False),
        sa.Column("seller_note", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column("confirmed_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.ForeignKeyConstraint(["arrangement_id"], ["fee_arrangement.id"]),
        sa.ForeignKeyConstraint(["confirmed_by_admin_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fee_payment_arrangement_id"), "fee_payment", ["arrangement_id"])
    op.create_index(op.f("ix_fee_payment_status"), "fee_payment", ["status"])

    op.create_table(
        "fee_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrangement_id", sa.Integer(), nullable=False),
        sa.Column("event_type", fee_event_type, nullable=False),
        sa.Column("amount_delta", sa.Float(), nullable=True),
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.Column("actor", sqlmodel.sql.sqltypes.AutoString(length=60), nullable=True),
        sa.ForeignKeyConstraint(["arrangement_id"], ["fee_arrangement.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fee_event_arrangement_id"), "fee_event", ["arrangement_id"])


def downgrade() -> None:
    op.drop_table("fee_event")
    op.drop_table("fee_payment")
    op.drop_table("fee_arrangement")
    op.drop_table("service_subscription_plan")
    op.drop_table("service_fee_config")
    op.drop_table("platform_fee_settings")
    for name in ("feeeventtype", "feepaymentstatus", "feepaymentkind", "arrangementstatus", "feemodel"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
