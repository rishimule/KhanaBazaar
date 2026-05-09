# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""split address fields

Revision ID: abc123456789
Revises: d6342a56eaf6
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "abc123456789"
down_revision: Union[str, Sequence[str], None] = "d6342a56eaf6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADDRESS_COLUMNS_REQUIRED = (
    ("address_line1", sa.String(length=120)),
    ("city", sa.String(length=80)),
    ("state", sa.String(length=80)),
    ("pincode", sa.String(length=10)),
    ("country", sa.String(length=60)),
)

ADDRESS_COLUMNS_OPTIONAL = (
    ("address_line2", sa.String(length=120)),
    ("landmark", sa.String(length=120)),
    ("latitude", sa.Float()),
    ("longitude", sa.Float()),
)


def upgrade() -> None:
    """Replace the free-text `address` column with structured fields.

    Pre-production only: truncates `sellerprofile` and `store` so the
    new NOT NULL columns can be added cleanly without placeholder
    defaults that would violate app-level validators.
    """
    op.execute("TRUNCATE sellerprofile, store RESTART IDENTITY CASCADE")

    op.drop_column("sellerprofile", "address")
    op.drop_column("store", "address")

    for table in ("sellerprofile", "store"):
        for name, col_type in ADDRESS_COLUMNS_REQUIRED:
            op.add_column(table, sa.Column(name, col_type, nullable=False))
        for name, col_type in ADDRESS_COLUMNS_OPTIONAL:
            op.add_column(table, sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    """Reverse the split. Lossy: structured data cannot be recombined."""
    for table in ("sellerprofile", "store"):
        for name, _col_type in ADDRESS_COLUMNS_OPTIONAL:
            op.drop_column(table, name)
        for name, _col_type in ADDRESS_COLUMNS_REQUIRED:
            op.drop_column(table, name)
        op.add_column(
            table,
            sa.Column("address", sa.String(), nullable=False, server_default=""),
        )
        op.alter_column(table, "address", server_default=None)
