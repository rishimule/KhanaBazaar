# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""per_store_per_service_checkout

Revision ID: c1a7f5e9b3d2
Revises: cecb3aa39b17
Create Date: 2026-05-10 20:00:00.000000

Pre-launch nuke of transactional tables (cart, cartitem, order, orderitem,
payment, delivery, review) so we can introduce NOT NULL service columns
without writing a backfill. Add `service_id` to Cart, `service_id` plus
`service_name_snapshot` to Order, and replace the Cart unique key.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1a7f5e9b3d2"
down_revision: Union[str, Sequence[str], None] = "cecb3aa39b17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Wipe transactional data. Pre-launch only — there is no production
    #    customer cart or order data to preserve.
    op.execute(
        "TRUNCATE TABLE review, payment, delivery, orderitem, \"order\", "
        "cartitem, cart RESTART IDENTITY CASCADE"
    )

    # 2. Cart: swap unique key and add service_id FK + index.
    op.drop_constraint("uq_cart_customer_store", "cart", type_="unique")
    op.add_column("cart", sa.Column("service_id", sa.Integer(), nullable=False))
    op.create_foreign_key(
        "fk_cart_service", "cart", "service", ["service_id"], ["id"],
    )
    op.create_index("ix_cart_service_id", "cart", ["service_id"])
    op.create_unique_constraint(
        "uq_cart_customer_store_service", "cart",
        ["customer_profile_id", "store_id", "service_id"],
    )

    # 3. Order: add service_id FK + index and frozen service name snapshot.
    op.add_column("order", sa.Column("service_id", sa.Integer(), nullable=False))
    op.add_column(
        "order", sa.Column("service_name_snapshot", sa.String(), nullable=False)
    )
    op.create_foreign_key(
        "fk_order_service", "order", "service", ["service_id"], ["id"],
    )
    op.create_index("ix_order_service_id", "order", ["service_id"])


def downgrade() -> None:
    op.execute(
        "TRUNCATE TABLE review, payment, delivery, orderitem, \"order\", "
        "cartitem, cart RESTART IDENTITY CASCADE"
    )
    op.drop_index("ix_order_service_id", "order")
    op.drop_constraint("fk_order_service", "order", type_="foreignkey")
    op.drop_column("order", "service_name_snapshot")
    op.drop_column("order", "service_id")
    op.drop_constraint("uq_cart_customer_store_service", "cart", type_="unique")
    op.drop_index("ix_cart_service_id", "cart")
    op.drop_constraint("fk_cart_service", "cart", type_="foreignkey")
    op.drop_column("cart", "service_id")
    op.create_unique_constraint(
        "uq_cart_customer_store", "cart", ["customer_profile_id", "store_id"],
    )
