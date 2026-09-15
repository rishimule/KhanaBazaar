"""seller upi payee

Revision ID: a1b2c3d4e5f6
Revises: f4d5e6a7b8c9
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f4d5e6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New CR group label. PG 15 permits ADD VALUE inside a transaction as long
    # as the new label is not *used* in the same transaction — it isn't here.
    op.execute(
        "ALTER TYPE sellerprofilechangegroup ADD VALUE IF NOT EXISTS 'payments'"
    )
    op.add_column(
        "sellerprofile", sa.Column("upi_vpa", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "sellerprofile", sa.Column("upi_qr_url", sa.String(length=2048), nullable=True)
    )
    op.add_column(
        "sellerprofile",
        sa.Column("upi_qr_storage_key", sa.String(length=512), nullable=True),
    )
    # NO backfill to True: there is no pre-existing payee to enable, so every
    # seller already in the database starts with UPI off (design spec §12).
    op.add_column(
        "sellerprofile",
        sa.Column(
            "upi_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "payment",
        sa.Column("customer_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment", "customer_claimed_at")
    op.drop_column("sellerprofile", "upi_enabled")
    op.drop_column("sellerprofile", "upi_qr_storage_key")
    op.drop_column("sellerprofile", "upi_qr_url")
    op.drop_column("sellerprofile", "upi_vpa")
    # Postgres cannot DROP an enum label; leaving 'payments' orphaned is safe.
