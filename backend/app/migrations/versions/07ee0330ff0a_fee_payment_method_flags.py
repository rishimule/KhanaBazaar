# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""fee payment method flags

Revision ID: 07ee0330ff0a
Revises: 9bb307d813e9
Create Date: 2026-07-22 15:15:43.450912

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '07ee0330ff0a'
down_revision: Union[str, Sequence[str], None] = '9bb307d813e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add per-method enable flags to the platform-fee settings singleton."""
    op.add_column(
        "platform_fee_settings",
        sa.Column(
            "upi_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "platform_fee_settings",
        sa.Column(
            "bank_transfer_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    """Drop the per-method enable flags."""
    op.drop_column("platform_fee_settings", "bank_transfer_enabled")
    op.drop_column("platform_fee_settings", "upi_enabled")
