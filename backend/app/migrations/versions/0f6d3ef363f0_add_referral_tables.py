# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add referral tables

Revision ID: 0f6d3ef363f0
Revises: 662ea92dac16
Create Date: 2026-07-09 16:01:25.869363

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0f6d3ef363f0"
down_revision: Union[str, Sequence[str], None] = "662ea92dac16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# New native enums for referrals (names == values, so create_all and this
# migration produce identical labels).
referral_status = postgresql.ENUM(
    "pending_review", "approved", "rejected", "active", "expired",
    name="referralstatus", create_type=False,
)
referral_target_role = postgresql.ENUM(
    "customer", "seller", name="referraltargetrole", create_type=False,
)
# `userrole` already exists (labels are PascalCase member NAMES) — reference
# it without creating.
user_role = postgresql.ENUM(
    "Customer", "Seller", "Admin", name="userrole", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    referral_status.create(bind, checkfirst=True)
    referral_target_role.create(bind, checkfirst=True)

    op.create_table(
        "referral_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "require_admin_approval", sa.Boolean(), nullable=False,
            server_default=sa.text("true"),
        ),
    )

    op.create_table(
        "referral",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_user_id", sa.Integer(), nullable=False),
        sa.Column("source_role", user_role, nullable=False),
        sa.Column("target_role", referral_target_role, nullable=False),
        sa.Column("invitee_name", sa.String(length=120), nullable=False),
        sa.Column("invitee_phone", sa.String(length=20), nullable=True),
        sa.Column("invitee_email", sa.String(length=254), nullable=True),
        sa.Column("location_state", sa.String(length=80), nullable=False),
        sa.Column("location_area", sa.String(length=160), nullable=False),
        sa.Column(
            "status", referral_status, nullable=False,
            server_default="pending_review",
        ),
        sa.Column("rejection_reason", sa.String(length=300), nullable=True),
        sa.Column("reviewed_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_user_id", sa.Integer(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_referral_source_user_id", "referral", ["source_user_id"])
    op.create_index("ix_referral_source_status", "referral", ["source_user_id", "status"])
    op.create_index("ix_referral_status", "referral", ["status"])
    # Block a second OPEN referral for the same contact; historical
    # rejected/expired rows may coexist.
    op.create_index(
        "uq_referral_open_email", "referral", ["invitee_email"], unique=True,
        postgresql_where=sa.text(
            "status IN ('pending_review','approved') AND invitee_email IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_referral_open_phone", "referral", ["invitee_phone"], unique=True,
        postgresql_where=sa.text(
            "status IN ('pending_review','approved') AND invitee_phone IS NOT NULL"
        ),
    )

    # `notificationtype` stores enum member NAMES (legacy convention), so add
    # the PascalCase name. IF NOT EXISTS makes it idempotent; PG15 allows
    # ADD VALUE inside the migration tx because we don't use it here.
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'Referral'")


def downgrade() -> None:
    op.drop_index("uq_referral_open_phone", table_name="referral")
    op.drop_index("uq_referral_open_email", table_name="referral")
    op.drop_index("ix_referral_status", table_name="referral")
    op.drop_index("ix_referral_source_status", table_name="referral")
    op.drop_index("ix_referral_source_user_id", table_name="referral")
    op.drop_table("referral")
    op.drop_table("referral_settings")
    bind = op.get_bind()
    referral_status.drop(bind, checkfirst=True)
    referral_target_role.drop(bind, checkfirst=True)
    # The `notificationtype` value 'Referral' is intentionally NOT removed
    # (PostgreSQL cannot drop enum values).
