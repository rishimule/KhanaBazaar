# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""generalize notification recipient (seller notifications + fee types)

Revision ID: 662ea92dac16
Revises: 343d1ef4da58
Create Date: 2026-07-05 18:22:54.505745

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "662ea92dac16"
down_revision: Union[str, Sequence[str], None] = "343d1ef4da58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New fee NotificationType values. `notificationtype` stores enum member
    # NAMES (legacy convention), so add the PascalCase names. IF NOT EXISTS makes
    # it idempotent; PG15 allows ADD VALUE inside the tx since we don't use them here.
    for name in ("FeeActivated", "FeeExpiring", "FeeSuspended"):
        op.execute(f"ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS '{name}'")

    # Recipient generalization on the live notification table.
    op.alter_column("notification", "customer_profile_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("notification", sa.Column("seller_profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_notification_seller_profile", "notification", "sellerprofile",
        ["seller_profile_id"], ["id"],
    )
    op.create_index(
        "ix_notification_seller_profile_id", "notification", ["seller_profile_id"]
    )
    op.create_index(
        "ix_notification_seller_created", "notification", ["seller_profile_id", "created_at"]
    )
    op.create_check_constraint(
        "ck_notification_one_recipient", "notification",
        "(customer_profile_id IS NOT NULL) <> (seller_profile_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_notification_one_recipient", "notification", type_="check")
    op.drop_index("ix_notification_seller_created", table_name="notification")
    op.drop_index("ix_notification_seller_profile_id", table_name="notification")
    op.drop_constraint("fk_notification_seller_profile", "notification", type_="foreignkey")
    op.drop_column("notification", "seller_profile_id")
    op.alter_column("notification", "customer_profile_id", existing_type=sa.Integer(), nullable=False)
    # No PG DROP VALUE — the added enum labels remain (harmless).
