# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add delivery eta columns

Revision ID: 801a251111fa
Revises: 4e5739351677
Create Date: 2026-05-30 16:44:03.655787

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '801a251111fa'
down_revision: Union[str, Sequence[str], None] = '4e5739351677'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add per-service delivery ETA window + order-level snapshot columns.

    Existing rows are backfilled via a temporary server_default (30/60),
    which is then dropped so the application layer is the source of truth.
    """
    op.add_column(
        "sellerprofile_service",
        sa.Column("delivery_eta_min_minutes", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "sellerprofile_service",
        sa.Column("delivery_eta_max_minutes", sa.Integer(), nullable=False, server_default="60"),
    )
    op.add_column(
        "order",
        sa.Column("delivery_eta_min_minutes", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "order",
        sa.Column("delivery_eta_max_minutes", sa.Integer(), nullable=False, server_default="60"),
    )
    op.alter_column("sellerprofile_service", "delivery_eta_min_minutes", server_default=None)
    op.alter_column("sellerprofile_service", "delivery_eta_max_minutes", server_default=None)
    op.alter_column("order", "delivery_eta_min_minutes", server_default=None)
    op.alter_column("order", "delivery_eta_max_minutes", server_default=None)


def downgrade() -> None:
    op.drop_column("order", "delivery_eta_max_minutes")
    op.drop_column("order", "delivery_eta_min_minutes")
    op.drop_column("sellerprofile_service", "delivery_eta_max_minutes")
    op.drop_column("sellerprofile_service", "delivery_eta_min_minutes")
