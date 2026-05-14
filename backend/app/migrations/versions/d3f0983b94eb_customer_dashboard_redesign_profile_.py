# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"""customer dashboard redesign profile prefs and review constraints

Revision ID: d3f0983b94eb
Revises: eeb39ac86872
Create Date: 2026-05-14 17:47:36.342417

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3f0983b94eb"
down_revision: Union[str, Sequence[str], None] = "eeb39ac86872"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add prefs columns to customerprofile + partial unique on review.order_id.

    Note: the `ck_review_rating_range` CHECK constraint already exists from
    a prior migration; not re-added here. Application-layer Pydantic
    validation also enforces the 1..5 range on review submission.
    """
    op.add_column(
        "customerprofile",
        sa.Column("preferred_language", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "customerprofile",
        sa.Column(
            "marketing_opt_in",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "customerprofile",
        sa.Column(
            "notify_order_email",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "customerprofile",
        sa.Column(
            "notify_order_sms",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "customerprofile",
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Partial unique: an order has at most one review; product/store reviews
    # without an order_id remain unconstrained.
    op.create_index(
        "uq_review_order_id",
        "review",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Reverse the upgrade."""
    op.drop_index("uq_review_order_id", table_name="review")
    op.drop_column("customerprofile", "phone_verified_at")
    op.drop_column("customerprofile", "notify_order_sms")
    op.drop_column("customerprofile", "notify_order_email")
    op.drop_column("customerprofile", "marketing_opt_in")
    op.drop_column("customerprofile", "preferred_language")
