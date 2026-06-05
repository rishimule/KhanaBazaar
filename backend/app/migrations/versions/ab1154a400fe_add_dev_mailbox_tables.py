# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add dev mailbox tables

Revision ID: ab1154a400fe
Revises: 1a82f642a321
Create Date: 2026-06-05 11:42:36.938953

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab1154a400fe'
down_revision: Union[str, Sequence[str], None] = '1a82f642a321'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "dev_email",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_email", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body_text", sa.String(), nullable=False),
        sa.Column("body_html", sa.String(), nullable=True),
        sa.Column("reply_to", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dev_email_to_email", "dev_email", ["to_email"])
    op.create_index("ix_dev_email_category", "dev_email", ["category"])

    op.create_table(
        "dev_sms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_phone", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dev_sms_to_phone", "dev_sms", ["to_phone"])
    op.create_index("ix_dev_sms_category", "dev_sms", ["category"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_dev_sms_category", table_name="dev_sms")
    op.drop_index("ix_dev_sms_to_phone", table_name="dev_sms")
    op.drop_table("dev_sms")
    op.drop_index("ix_dev_email_category", table_name="dev_email")
    op.drop_index("ix_dev_email_to_email", table_name="dev_email")
    op.drop_table("dev_email")
