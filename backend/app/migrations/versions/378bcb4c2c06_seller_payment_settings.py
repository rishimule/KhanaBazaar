# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""seller payment settings

Revision ID: 378bcb4c2c06
Revises: 4675f7be7055
Create Date: 2026-10-07 10:00:00.000000

Seller payment settings (spec 2026-10-07). Store-wide switches for cash on
delivery and pay at store beside the existing UPI / bank-transfer ones (both
start on, so nothing changes until a seller turns one off); a generation
counter per payee switch, bumped on every on→off; and the payee copied onto
each order's payment row at placement. Constant defaults: no table rewrite.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "378bcb4c2c06"
down_revision: Union[str, Sequence[str], None] = "4675f7be7055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sellerprofile",
        sa.Column("cod_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "sellerprofile",
        sa.Column(
            "pay_at_store_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
    )
    op.add_column(
        "sellerprofile",
        sa.Column("upi_generation", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "sellerprofile",
        sa.Column(
            "bank_transfer_generation", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column("payment", sa.Column("payee_upi_vpa", sa.String(length=120), nullable=True))
    op.add_column("payment", sa.Column("payee_upi_name", sa.String(), nullable=True))
    op.add_column("payment", sa.Column("payee_upi_generation", sa.Integer(), nullable=True))
    op.add_column(
        "payment", sa.Column("payee_bank_account_name", sa.String(length=140), nullable=True)
    )
    op.add_column("payment", sa.Column("payee_bank_account_number", sa.String(), nullable=True))
    op.add_column("payment", sa.Column("payee_bank_ifsc", sa.String(), nullable=True))
    op.add_column("payment", sa.Column("payee_bank_generation", sa.Integer(), nullable=True))


def downgrade() -> None:
    for column in (
        "payee_bank_generation",
        "payee_bank_ifsc",
        "payee_bank_account_number",
        "payee_bank_account_name",
        "payee_upi_generation",
        "payee_upi_name",
        "payee_upi_vpa",
    ):
        op.drop_column("payment", column)
    for column in (
        "bank_transfer_generation",
        "upi_generation",
        "pay_at_store_enabled",
        "cod_enabled",
    ):
        op.drop_column("sellerprofile", column)
