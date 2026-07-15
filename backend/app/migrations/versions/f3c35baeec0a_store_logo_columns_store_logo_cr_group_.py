# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""store logo columns + store_logo cr group value

Revision ID: f3c35baeec0a
Revises: 932c4bd8aa24
Create Date: 2026-07-12 20:25:05.482294

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3c35baeec0a'
down_revision: Union[str, Sequence[str], None] = '932c4bd8aa24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add store logo columns + the store_logo CR group value."""
    op.add_column("store", sa.Column("logo_url", sa.String(length=2048), nullable=True))
    op.add_column(
        "store", sa.Column("logo_storage_key", sa.String(length=512), nullable=True)
    )
    # Native PG enum `sellerprofilechangegroup` stores the member VALUE. Add the
    # new member so store-logo change-requests can be inserted. The value is
    # only USED after this migration commits, which PG 15 permits in-transaction
    # (same pattern as the 'avatar' member in 8dc9ba5723f1).
    op.execute(
        "ALTER TYPE sellerprofilechangegroup ADD VALUE IF NOT EXISTS 'store_logo'"
    )


def downgrade() -> None:
    """Drop the store logo columns (PG cannot easily DROP an enum value)."""
    op.drop_column("store", "logo_storage_key")
    op.drop_column("store", "logo_url")
    # 'store_logo' is intentionally left in sellerprofilechangegroup — PG has no
    # safe DROP VALUE, and leaving it is harmless.
