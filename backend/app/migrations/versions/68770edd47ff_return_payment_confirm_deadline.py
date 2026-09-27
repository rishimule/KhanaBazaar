# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""return payment confirm deadline

Revision ID: 68770edd47ff
Revises: befaea61269d
Create Date: 2026-09-26 18:20:42.069713

A cash return parked in `awaiting_payment_confirmation` had no deadline, so a
customer who never confirmed the money arrived held it open forever. The new
column is stamped at acceptance; the hourly returns sweep closes the return
once it passes.

Returns already parked when this ships get a full window from deploy rather
than all closing on the first sweep after it. The 7 days mirrors the default
of `RETURN_PAYMENT_CONFIRM_DAYS`; a migration cannot read runtime settings.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '68770edd47ff'
down_revision: Union[str, Sequence[str], None] = 'befaea61269d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "return_request",
        sa.Column(
            "payment_confirm_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.execute(
        "UPDATE return_request "
        "SET payment_confirm_expires_at = now() + interval '7 days' "
        "WHERE status = 'awaiting_payment_confirmation' "
        "AND payment_confirm_expires_at IS NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("return_request", "payment_confirm_expires_at")
