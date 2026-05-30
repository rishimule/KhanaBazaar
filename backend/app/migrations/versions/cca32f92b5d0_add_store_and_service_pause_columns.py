# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add store and service pause columns

Revision ID: cca32f92b5d0
Revises: 801a251111fa
Create Date: 2026-05-30 18:15:02.937053

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cca32f92b5d0'
down_revision: Union[str, Sequence[str], None] = '801a251111fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "store",
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "store",
        sa.Column("pause_reason", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "store",
        sa.Column("paused_until", sa.Date(), nullable=True),
    )
    op.add_column(
        "sellerprofile_service",
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "sellerprofile_service",
        sa.Column("pause_reason", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "sellerprofile_service",
        sa.Column("paused_until", sa.Date(), nullable=True),
    )
    # Drop the server default now that existing rows are backfilled — the
    # app-level model default governs new rows.
    op.alter_column("store", "is_paused", server_default=None)
    op.alter_column("sellerprofile_service", "is_paused", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sellerprofile_service", "paused_until")
    op.drop_column("sellerprofile_service", "pause_reason")
    op.drop_column("sellerprofile_service", "is_paused")
    op.drop_column("store", "paused_until")
    op.drop_column("store", "pause_reason")
    op.drop_column("store", "is_paused")
