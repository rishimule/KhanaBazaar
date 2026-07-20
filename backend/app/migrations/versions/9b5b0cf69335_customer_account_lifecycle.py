# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""customer account lifecycle

Revision ID: 9b5b0cf69335
Revises: 9383edc91f22
Create Date: 2026-07-20 18:38:42.832171

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9b5b0cf69335'
down_revision: Union[str, Sequence[str], None] = '9383edc91f22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    account_status = postgresql.ENUM(
        "active", "deactivated", "suspended", "deleted", name="accountstatus"
    )
    account_status.create(op.get_bind(), checkfirst=True)

    bind_enum = postgresql.ENUM(
        "active", "deactivated", "suspended", "deleted",
        name="accountstatus", create_type=False,
    )
    op.add_column(
        "user",
        sa.Column("account_status", bind_enum, nullable=False, server_default="active"),
    )
    op.add_column("user", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("status_reason", sa.String(length=500), nullable=True))
    op.add_column("user", sa.Column("status_changed_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_user_status_changed_by_user", "user", "user",
        ["status_changed_by_user_id"], ["id"],
    )
    op.create_index("ix_user_account_status", "user", ["account_status"])

    op.create_table(
        "customer_account_event",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("actor_role", sa.String(length=16), nullable=False),
        sa.Column("from_status", bind_enum, nullable=False),
        sa.Column("to_status", bind_enum, nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_customer_account_event_user_id", "customer_account_event", ["user_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_customer_account_event_user_id", table_name="customer_account_event")
    op.drop_table("customer_account_event")
    op.drop_index("ix_user_account_status", table_name="user")
    op.drop_constraint("fk_user_status_changed_by_user", "user", type_="foreignkey")
    op.drop_column("user", "status_changed_by_user_id")
    op.drop_column("user", "status_reason")
    op.drop_column("user", "status_changed_at")
    op.drop_column("user", "account_status")
    postgresql.ENUM(name="accountstatus").drop(op.get_bind(), checkfirst=True)
