# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.notification_campaign import CampaignStatus, NotificationAudience

_VALID_CHANNELS = {"in_app", "email", "sms"}


def _validate_channels(channels: list[str]) -> list[str]:
    bad = set(channels) - _VALID_CHANNELS
    if bad:
        raise ValueError(f"invalid_channels: {sorted(bad)}")
    if "in_app" not in channels:
        raise ValueError("in_app_channel_required")
    return channels


def _validate_cta_url(cta_url: str | None) -> None:
    """CTA links render as an <a href> in the notification bell, so only allow
    http(s) schemes (reject javascript:/data: etc.)."""
    if cta_url and not cta_url.startswith(("http://", "https://")):
        raise ValueError("cta_url_must_be_http")


class CampaignCreate(BaseModel):
    audience: NotificationAudience
    filters: dict[str, Any] = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=lambda: ["in_app"])
    title: str = Field(min_length=1, max_length=140)
    body: str = Field(min_length=1, max_length=2000)
    cta_url: Optional[str] = Field(default=None, max_length=500)
    cta_label: Optional[str] = Field(default=None, max_length=80)
    is_essential: bool = False

    @model_validator(mode="after")
    def _check(self) -> "CampaignCreate":
        _validate_channels(self.channels)
        _validate_cta_url(self.cta_url)
        return self


class CampaignUpdate(BaseModel):
    audience: Optional[NotificationAudience] = None
    filters: Optional[dict[str, Any]] = None
    channels: Optional[list[str]] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=140)
    body: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    cta_url: Optional[str] = Field(default=None, max_length=500)
    cta_label: Optional[str] = Field(default=None, max_length=80)
    is_essential: Optional[bool] = None

    @model_validator(mode="after")
    def _check(self) -> "CampaignUpdate":
        if self.channels is not None:
            _validate_channels(self.channels)
        _validate_cta_url(self.cta_url)
        return self


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    audience: NotificationAudience
    filters: dict[str, Any]
    channels: list[str]
    title: str
    body: str
    image_url: Optional[str] = None
    cta_url: Optional[str] = None
    cta_label: Optional[str] = None
    is_essential: bool
    status: CampaignStatus
    recipients_targeted: int
    inapp_created: int
    email_enqueued: int
    sms_enqueued: int
    created_at: datetime
    sent_at: Optional[datetime] = None


class AudienceCount(BaseModel):
    customers: int
    sellers: int
