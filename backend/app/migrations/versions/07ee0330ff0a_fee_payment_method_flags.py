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
    """Add per-method enable flags to the platform-fee settings singleton.

    New rows default False (a method is offered only once explicitly enabled).
    Existing rows are backfilled to True where the method's payee details are
    already present, so installs configured before this migration keep offering
    those methods with no behavioral regression.
    """
    op.add_column(
        "platform_fee_settings",
        sa.Column(
            "upi_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "platform_fee_settings",
        sa.Column(
            "bank_transfer_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # NULLIF(x, '') so an empty-string payee field counts as absent, matching
    # the app's truthiness guard — otherwise a pre-existing '' row would backfill
    # to enabled+incomplete and then block every subsequent settings PATCH.
    op.execute(
        "UPDATE platform_fee_settings SET upi_enabled = TRUE "
        "WHERE NULLIF(upi_id, '') IS NOT NULL OR NULLIF(qr_image_url, '') IS NOT NULL"
    )
    op.execute(
        "UPDATE platform_fee_settings SET bank_transfer_enabled = TRUE "
        "WHERE NULLIF(bank_account_number, '') IS NOT NULL "
        "AND NULLIF(bank_ifsc, '') IS NOT NULL"
    )


def downgrade() -> None:
    """Drop the per-method enable flags."""
    op.drop_column("platform_fee_settings", "bank_transfer_enabled")
    op.drop_column("platform_fee_settings", "upi_enabled")
