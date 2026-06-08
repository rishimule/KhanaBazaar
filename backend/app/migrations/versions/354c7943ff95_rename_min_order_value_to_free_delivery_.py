# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""rename min order value to free delivery threshold add delivery fee

Revision ID: 354c7943ff95
Revises: ab1154a400fe
Create Date: 2026-06-08 17:15:23.130421

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '354c7943ff95'
down_revision: Union[str, Sequence[str], None] = 'ab1154a400fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sellerprofile_service",
        "min_order_value",
        new_column_name="free_delivery_threshold",
    )
    op.add_column(
        "sellerprofile_service",
        sa.Column("delivery_fee", sa.Float(), nullable=False, server_default="0"),
    )
    # Backfill: every existing service starts charging a flat ₹10 below its
    # (renamed) free-delivery threshold. New rows fall back to the model default.
    op.execute("UPDATE sellerprofile_service SET delivery_fee = 10")
    op.alter_column("sellerprofile_service", "delivery_fee", server_default=None)


def downgrade() -> None:
    op.drop_column("sellerprofile_service", "delivery_fee")
    op.alter_column(
        "sellerprofile_service",
        "free_delivery_threshold",
        new_column_name="min_order_value",
    )
