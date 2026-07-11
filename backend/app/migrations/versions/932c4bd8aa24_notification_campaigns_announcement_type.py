# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""notification campaigns + announcement type

Revision ID: 932c4bd8aa24
Revises: 36dcf8e48719
Create Date: 2026-07-11 15:53:12.135090

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '932c4bd8aa24'
down_revision: Union[str, Sequence[str], None] = '36dcf8e48719'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # notificationtype stores the member NAME (see schema.sql header).
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'Announcement'")

    audience = postgresql.ENUM(
        "customers", "sellers", "both", name="notificationaudience"
    )
    status = postgresql.ENUM(
        "draft", "sending", "sent", "failed", name="campaignstatus"
    )
    audience.create(op.get_bind(), checkfirst=True)
    status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "notification_campaign",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "audience",
            postgresql.ENUM(name="notificationaudience", create_type=False),
            nullable=False,
        ),
        sa.Column("filters", postgresql.JSONB, nullable=False),
        sa.Column("channels", postgresql.JSONB, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("body", sa.String, nullable=False),
        sa.Column("image_url", sa.String(length=500)),
        sa.Column("image_storage_key", sa.String(length=300)),
        sa.Column("cta_url", sa.String(length=500)),
        sa.Column("cta_label", sa.String(length=80)),
        sa.Column(
            "is_essential", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="campaignstatus", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("recipients_targeted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("inapp_created", sa.Integer, nullable=False, server_default="0"),
        sa.Column("email_enqueued", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sms_enqueued", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_by_admin_id",
            sa.Integer,
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_notification_campaign_status", "notification_campaign", ["status"]
    )

    op.add_column(
        "notification",
        sa.Column(
            "campaign_id",
            sa.Integer,
            sa.ForeignKey("notification_campaign.id"),
            nullable=True,
        ),
    )
    op.add_column("notification", sa.Column("image_url", sa.String(length=500)))
    op.add_column("notification", sa.Column("cta_url", sa.String(length=500)))
    op.add_column("notification", sa.Column("cta_label", sa.String(length=80)))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("notification", "cta_label")
    op.drop_column("notification", "cta_url")
    op.drop_column("notification", "image_url")
    op.drop_column("notification", "campaign_id")
    op.drop_index(
        "ix_notification_campaign_status", table_name="notification_campaign"
    )
    op.drop_table("notification_campaign")
    op.execute("DROP TYPE IF EXISTS campaignstatus")
    op.execute("DROP TYPE IF EXISTS notificationaudience")
    # notificationtype 'Announcement' value cannot be removed (PG limitation).
