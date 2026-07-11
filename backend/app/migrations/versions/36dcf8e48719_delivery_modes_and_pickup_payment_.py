# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""delivery modes and pickup payment methods

Revision ID: 36dcf8e48719
Revises: f6495e1b1c31
Create Date: 2026-07-11 11:33:08.595346

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '36dcf8e48719'
down_revision: Union[str, Sequence[str], None] = 'f6495e1b1c31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Native PG enums store the Python member NAME (see schema.sql header).
    # Add the CamelCase names; the JSON API/frontend use the snake_case values.
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'NetBanking'")
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'PayAtStore'")

    deliverymode = postgresql.ENUM("DoorDelivery", "Pickup", name="deliverymode")
    deliverymode.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "order",
        sa.Column(
            "delivery_mode",
            postgresql.ENUM(
                "DoorDelivery", "Pickup", name="deliverymode", create_type=False
            ),
            nullable=False,
            server_default="DoorDelivery",
        ),
    )
    op.add_column(
        "sellerprofile_service",
        sa.Column(
            "pickup_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sellerprofile_service", "pickup_enabled")
    op.drop_column("order", "delivery_mode")
    op.execute("DROP TYPE IF EXISTS deliverymode")
    # NOTE: PostgreSQL cannot drop individual enum values; the added
    # paymentmethod values ('NetBanking','PayAtStore') remain on downgrade.
