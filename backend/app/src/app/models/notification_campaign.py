# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Admin bulk-notification campaign model. Enums use `values_callable` so the
native PG enum stores the lowercase VALUES (mirrors `platform_fee.py`)."""
import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseSchema


class NotificationAudience(str, enum.Enum):
    Customers = "customers"
    Sellers = "sellers"
    Both = "both"


class CampaignStatus(str, enum.Enum):
    Draft = "draft"
    Sending = "sending"
    Sent = "sent"
    Failed = "failed"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Serialize enum members by VALUE (snake_case PG labels)."""
    return [m.value for m in enum_cls]


class NotificationCampaign(BaseSchema, table=True):
    __tablename__ = "notification_campaign"
    audience: NotificationAudience = Field(
        sa_column=Column(
            SAEnum(
                NotificationAudience,
                name="notificationaudience",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
        )
    )
    # filters: {state?, cities?[], new_onboarded?, seller_fee_models?[], seller_expiring_soon?}
    filters: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    # channels: always includes "in_app"; plus any of "email", "sms".
    channels: list[str] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    title: str = Field(nullable=False)
    body: str = Field(nullable=False)
    image_url: Optional[str] = Field(default=None, max_length=500)
    image_storage_key: Optional[str] = Field(default=None, max_length=300)
    cta_url: Optional[str] = Field(default=None, max_length=500)
    cta_label: Optional[str] = Field(default=None, max_length=80)
    is_essential: bool = Field(default=False, nullable=False)
    status: CampaignStatus = Field(
        default=CampaignStatus.Draft,
        sa_column=Column(
            SAEnum(
                CampaignStatus,
                name="campaignstatus",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
            index=True,
        ),
    )
    recipients_targeted: int = Field(default=0, nullable=False)
    inapp_created: int = Field(default=0, nullable=False)
    email_enqueued: int = Field(default=0, nullable=False)
    sms_enqueued: int = Field(default=0, nullable=False)
    created_by_admin_id: int = Field(foreign_key="user.id", nullable=False)
    sent_at: Optional[datetime] = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )
