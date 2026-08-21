# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""return order management: requests, items, events, customer store credit

Revision ID: c1a2b3d4e5f6
Revises: b4c1d2e3f5a6
Create Date: 2026-08-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b4c1d2e3f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# postgresql.ENUM(create_type=False) + explicit pre-create — mirrors 9bb307d813e9
# / 343d1ef4da58. Without create_type=False, create_table re-issues CREATE TYPE
# for every enum column and collides with the pre-create.
# Labels are the model member NAMES (lowercase, equal to their values).
_RETURN_STATUS = postgresql.ENUM(
    "awaiting_customer_confirmation", "active", "awaiting_payment_confirmation",
    "closed", "rejected", "withdrawn", "expired",
    name="returnstatus", create_type=False,
)
_INITIATOR = postgresql.ENUM(
    "customer", "seller", "admin", name="returninitiator", create_type=False,
)
_SETTLEMENT = postgresql.ENUM(
    "payment", "store_credit", name="returnsettlementchoice", create_type=False,
)
_REASON = postgresql.ENUM(
    "damaged", "wrong_item", "past_expiry", "quality_issue", "not_as_described",
    "other", name="returnreasoncode", create_type=False,
)
_ENTRY_TYPE = postgresql.ENUM(
    "return_credit", "order_applied", "order_reverted", "admin_adjust",
    name="storecreditentrytype", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (_RETURN_STATUS, _INITIATOR, _SETTLEMENT, _REASON, _ENTRY_TYPE):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "return_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=False),
        sa.Column("customer_profile_id", sa.Integer(), sa.ForeignKey("customerprofile.id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("store.id"), nullable=False),
        sa.Column("seller_profile_id", sa.Integer(), sa.ForeignKey("sellerprofile.id"), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("service.id"), nullable=False),
        sa.Column("initiated_by", _INITIATOR, nullable=False),
        sa.Column("initiated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("status", _RETURN_STATUS, nullable=False),
        sa.Column("is_full_order", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason_code", _REASON, nullable=False),
        sa.Column("reason_note", sa.String(length=500), nullable=True),
        sa.Column("items_amount", sa.Float(), nullable=False),
        sa.Column("delivery_fee_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("settlement_choice", _SETTLEMENT, nullable=False),
        sa.Column("credit_reversal_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("store_credit_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("payment_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("agreement_policy_version", sa.Integer(), nullable=False),
        sa.Column("agreement_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirm_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handover_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipt_otp", sa.String(length=6), nullable=True),
        sa.Column("receipt_otp_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("receipt_otp_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipt_otp_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restock", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_return_request_order_id", "return_request", ["order_id"])
    op.create_index("ix_return_request_customer_profile_id", "return_request", ["customer_profile_id"])
    op.create_index("ix_return_request_store_id", "return_request", ["store_id"])
    op.create_index("ix_return_request_seller_profile_id", "return_request", ["seller_profile_id"])
    op.create_index("ix_return_request_service_id", "return_request", ["service_id"])
    op.create_index("ix_return_request_status", "return_request", ["status"])
    op.create_index("ix_return_request_customer_created", "return_request", ["customer_profile_id", "created_at"])
    op.create_index("ix_return_request_seller_status", "return_request", ["seller_profile_id", "status"])
    op.create_index("ix_return_request_store_status", "return_request", ["store_id", "status"])

    op.create_table(
        "return_request_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("return_request_id", sa.Integer(), sa.ForeignKey("return_request.id"), nullable=False),
        sa.Column("order_item_id", sa.Integer(), sa.ForeignKey("orderitem.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("product_name_snapshot", sa.String(), nullable=False),
        sa.Column("unit_price_snapshot", sa.Float(), nullable=False),
        sa.Column("line_total", sa.Float(), nullable=False),
        sa.UniqueConstraint("return_request_id", "order_item_id", name="uq_return_item_request_orderitem"),
    )
    op.create_index("ix_return_request_item_return_request_id", "return_request_item", ["return_request_id"])
    op.create_index("ix_return_request_item_order_item_id", "return_request_item", ["order_item_id"])

    op.create_table(
        "return_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("return_request_id", sa.Integer(), sa.ForeignKey("return_request.id"), nullable=False),
        sa.Column("from_status", _RETURN_STATUS, nullable=True),
        sa.Column("to_status", _RETURN_STATUS, nullable=False),
        sa.Column("actor_role", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_return_event_return_request_id", "return_event", ["return_request_id"])
    op.create_index("ix_return_event_request_created", "return_event", ["return_request_id", "created_at"])

    op.create_table(
        "customer_store_credit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seller_profile_id", sa.Integer(), sa.ForeignKey("sellerprofile.id"), nullable=False),
        sa.Column("customer_profile_id", sa.Integer(), sa.ForeignKey("customerprofile.id"), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("lifetime_earned", sa.Float(), nullable=False, server_default="0"),
        sa.Column("lifetime_spent", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint("seller_profile_id", "customer_profile_id", name="uq_customer_store_credit_pair"),
    )
    op.create_index("ix_customer_store_credit_seller_profile_id", "customer_store_credit", ["seller_profile_id"])
    op.create_index("ix_customer_store_credit_customer", "customer_store_credit", ["customer_profile_id"])

    op.create_table(
        "customer_store_credit_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("customer_store_credit.id"), nullable=False),
        sa.Column("entry_type", _ENTRY_TYPE, nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("balance_after", sa.Float(), nullable=False),
        sa.Column("return_request_id", sa.Integer(), sa.ForeignKey("return_request.id"), nullable=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_customer_store_credit_entry_account_id", "customer_store_credit_entry", ["account_id"])
    op.create_index("ix_customer_store_credit_entry_acct_created", "customer_store_credit_entry", ["account_id", "created_at"])

    op.add_column(
        "sellerprofile_service",
        sa.Column("return_window_days", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "order",
        sa.Column("store_credit_applied", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("order", "store_credit_applied")
    op.drop_column("sellerprofile_service", "return_window_days")
    op.drop_table("customer_store_credit_entry")
    op.drop_table("customer_store_credit")
    op.drop_table("return_event")
    op.drop_table("return_request_item")
    op.drop_table("return_request")
    bind = op.get_bind()
    for enum_type in (_ENTRY_TYPE, _REASON, _SETTLEMENT, _INITIATOR, _RETURN_STATUS):
        enum_type.drop(bind, checkfirst=True)
