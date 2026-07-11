# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from app.models.notification import NotificationType
from app.models.notification_campaign import CampaignStatus, NotificationAudience


def test_campaign_enum_values() -> None:
    assert {a.value for a in NotificationAudience} == {"customers", "sellers", "both"}
    assert {s.value for s in CampaignStatus} == {"draft", "sending", "sent", "failed"}


def test_announcement_notification_type() -> None:
    assert NotificationType.Announcement.value == "announcement"
