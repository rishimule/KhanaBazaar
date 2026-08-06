# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""seller new-order notification type

Revision ID: b4c1d2e3f5a6
Revises: 07ee0330ff0a
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b4c1d2e3f5a6"
down_revision: Union[str, Sequence[str], None] = "07ee0330ff0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `notificationtype` stores enum member NAMES (legacy convention), so add
    # the PascalCase name. IF NOT EXISTS makes it idempotent; PG15 allows
    # ADD VALUE inside the tx since the label is not used in this migration.
    op.execute(
        "ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'SellerNewOrder'"
    )


def downgrade() -> None:
    # No PG DROP VALUE — the added enum label remains (harmless).
    pass
