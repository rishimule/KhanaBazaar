# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add dev_whatsapp table

Revision ID: c3f2a1b4d5e6
Revises: 8dc9ba5723f1
Create Date: 2026-06-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3f2a1b4d5e6"
down_revision: Union[str, Sequence[str], None] = "8dc9ba5723f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dev_whatsapp",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_phone", sa.String(), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("template", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dev_whatsapp_to_phone", "dev_whatsapp", ["to_phone"])
    op.create_index("ix_dev_whatsapp_template", "dev_whatsapp", ["template"])
    op.create_index("ix_dev_whatsapp_category", "dev_whatsapp", ["category"])


def downgrade() -> None:
    op.drop_index("ix_dev_whatsapp_category", table_name="dev_whatsapp")
    op.drop_index("ix_dev_whatsapp_template", table_name="dev_whatsapp")
    op.drop_index("ix_dev_whatsapp_to_phone", table_name="dev_whatsapp")
    op.drop_table("dev_whatsapp")
