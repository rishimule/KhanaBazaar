# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""return notification types + notification.return_request_id

Revision ID: f4d5e6a7b8c9
Revises: e3c4d5f6a7b8
Create Date: 2026-08-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4d5e6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "e3c4d5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `notificationtype` stores enum member NAMES (PascalCase, legacy
    # convention). IF NOT EXISTS keeps this idempotent.
    for label in ("ReturnStatusUpdate", "ReturnReceiptOtp", "SellerReturnRequest"):
        op.execute(f"ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS '{label}'")
    op.add_column(
        "notification",
        sa.Column(
            "return_request_id",
            sa.Integer(),
            sa.ForeignKey("return_request.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("notification", "return_request_id")
    # No PG DROP VALUE — the added enum labels remain (harmless).
