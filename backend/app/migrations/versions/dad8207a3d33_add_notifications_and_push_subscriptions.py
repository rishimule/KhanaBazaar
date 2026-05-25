# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""add notifications and push subscriptions

Revision ID: dad8207a3d33
Revises: c6af6b06e7dd
Create Date: 2026-05-24 20:12:29.882352

Hand-written: autogenerate swept in unrelated PostGIS/tiger + trigram-index
drift from the dev database. This migration creates ONLY the two new tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'dad8207a3d33'
down_revision: Union[str, Sequence[str], None] = 'c6af6b06e7dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pushsubscription',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('customer_profile_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.String(), nullable=False),
        sa.Column('p256dh', sa.String(), nullable=False),
        sa.Column('auth', sa.String(), nullable=False),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_profile_id'], ['customerprofile.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_pushsubscription_customer_profile_id'),
        'pushsubscription', ['customer_profile_id'], unique=False,
    )
    op.create_index(
        op.f('ix_pushsubscription_endpoint'),
        'pushsubscription', ['endpoint'], unique=True,
    )

    op.create_table(
        'notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('customer_profile_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column(
            'type',
            sa.Enum('OrderStatus', name='notificationtype'),
            nullable=False,
        ),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.String(), nullable=False),
        sa.Column('status_value', sa.String(), nullable=False),
        sa.Column('read', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['customer_profile_id'], ['customerprofile.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['order.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_notification_customer_created',
        'notification', ['customer_profile_id', 'created_at'], unique=False,
    )
    op.create_index(
        op.f('ix_notification_customer_profile_id'),
        'notification', ['customer_profile_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_notification_customer_profile_id'), table_name='notification')
    op.drop_index('ix_notification_customer_created', table_name='notification')
    op.drop_table('notification')
    op.drop_index(op.f('ix_pushsubscription_endpoint'), table_name='pushsubscription')
    op.drop_index(
        op.f('ix_pushsubscription_customer_profile_id'), table_name='pushsubscription'
    )
    op.drop_table('pushsubscription')
    # sa.Enum-created PG type is not auto-dropped by drop_table.
    sa.Enum(name='notificationtype').drop(op.get_bind(), checkfirst=True)
