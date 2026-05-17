# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add admin_action_log

Revision ID: 81ccebe49ed1
Revises: dd5dd06d2862
Create Date: 2026-05-16 18:29:35.587450

Adds the ``admin_action_log`` table for the admin seller-supervisor audit
trail. Schema-only migration; no data backfill. Pre-existing drift between
the current schema and other model files is intentionally NOT included here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "81ccebe49ed1"
down_revision: Union[str, Sequence[str], None] = "dd5dd06d2862"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "admin_action_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("target_seller_id", sa.Integer(), nullable=False),
        sa.Column(
            "target_type",
            sa.Enum(
                "Inventory",
                "Order",
                "Store",
                "SellerProfile",
                name="adminactiontargettype",
            ),
            nullable=False,
        ),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column(
            "action", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False
        ),
        sa.Column(
            "before_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "after_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "reason", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["target_seller_id"], ["sellerprofile.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_admin_action_log_admin_user_id"),
        "admin_action_log",
        ["admin_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_action_log_seller_created",
        "admin_action_log",
        ["target_seller_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_admin_action_log_seller_created", table_name="admin_action_log"
    )
    op.drop_index(
        op.f("ix_admin_action_log_admin_user_id"), table_name="admin_action_log"
    )
    op.drop_table("admin_action_log")
    sa.Enum(name="adminactiontargettype").drop(op.get_bind(), checkfirst=True)
