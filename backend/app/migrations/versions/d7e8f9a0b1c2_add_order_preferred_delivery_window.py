# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add order preferred delivery window

Revision ID: d7e8f9a0b1c2
Revises: c3f2a1b4d5e6
Create Date: 2026-06-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "c3f2a1b4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "order",
        sa.Column("preferred_delivery_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "order",
        sa.Column("preferred_delivery_window", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order", "preferred_delivery_window")
    op.drop_column("order", "preferred_delivery_date")
