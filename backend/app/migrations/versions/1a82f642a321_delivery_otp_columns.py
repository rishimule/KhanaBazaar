# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""delivery otp columns

Revision ID: 1a82f642a321
Revises: cca32f92b5d0
Create Date: 2026-06-02 10:21:47.473215

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1a82f642a321'
down_revision: Union[str, Sequence[str], None] = 'cca32f92b5d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add delivery-handover OTP columns + the DeliveryOtp notification enum value."""
    # Native PG enum `notificationtype` stores the member NAME. Add the new
    # member so DeliveryOtp notifications can be inserted. IF NOT EXISTS keeps
    # this idempotent; PG 15 allows ADD VALUE inside the migration transaction
    # because the value is not used until after commit.
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'DeliveryOtp'")
    op.add_column(
        'delivery',
        sa.Column('delivery_otp', sa.String(length=6), nullable=True),
    )
    op.add_column(
        'delivery',
        sa.Column(
            'delivery_otp_attempts',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )
    op.add_column(
        'delivery',
        sa.Column('delivery_otp_sent_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'delivery',
        sa.Column(
            'delivery_otp_verified_at', sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    """Drop delivery-handover OTP columns.

    The `notificationtype` enum value `DeliveryOtp` is intentionally NOT
    removed — Postgres has no DROP VALUE, and dropping it would require
    recreating the type. Leaving an unused enum label is harmless.
    """
    op.drop_column('delivery', 'delivery_otp_verified_at')
    op.drop_column('delivery', 'delivery_otp_sent_at')
    op.drop_column('delivery', 'delivery_otp_attempts')
    op.drop_column('delivery', 'delivery_otp')
