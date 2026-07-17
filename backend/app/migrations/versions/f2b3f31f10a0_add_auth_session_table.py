# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add auth_session table

Revision ID: f2b3f31f10a0
Revises: f3c35baeec0a
Create Date: 2026-07-17 11:51:55.253286

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b3f31f10a0'
down_revision: Union[str, Sequence[str], None] = 'f3c35baeec0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "auth_session",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False),
        sa.Column("refresh_token_hash", sa.String, nullable=False),
        sa.Column("prev_token_hash", sa.String, nullable=True),
        sa.Column("prev_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "trusted", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_label", sa.String, nullable=False, server_default=""),
        sa.Column("user_agent", sa.String, nullable=False, server_default=""),
        sa.Column("ip", sa.String, nullable=True),
    )
    op.create_index("ix_auth_session_user_id", "auth_session", ["user_id"])
    op.create_index(
        "ix_auth_session_refresh_token_hash", "auth_session", ["refresh_token_hash"]
    )
    op.create_index(
        "ix_auth_session_prev_token_hash", "auth_session", ["prev_token_hash"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_auth_session_prev_token_hash", table_name="auth_session")
    op.drop_index("ix_auth_session_refresh_token_hash", table_name="auth_session")
    op.drop_index("ix_auth_session_user_id", table_name="auth_session")
    op.drop_table("auth_session")
