# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from pydantic import ValidationError

from app.models.referral import ReferralTargetRole
from app.schemas.referrals import ReferralCreate


def test_requires_at_least_one_contact():
    with pytest.raises(ValidationError):
        ReferralCreate(
            target_role=ReferralTargetRole.customer,
            invitee_name="Asha",
            location_state="Maharashtra",
            location_area="Pune",
        )


def test_rejects_unknown_state():
    with pytest.raises(ValidationError):
        ReferralCreate(
            target_role=ReferralTargetRole.customer,
            invitee_name="Asha",
            invitee_email="a@b.com",
            location_state="Atlantis",
            location_area="Pune",
        )


def test_rejects_bad_phone():
    with pytest.raises(ValidationError):
        ReferralCreate(
            target_role=ReferralTargetRole.customer,
            invitee_name="Asha",
            invitee_phone="98 123-45678",  # not +91 E.164
            location_state="Maharashtra",
            location_area="Pune",
        )


def test_normalizes_phone_and_lowercases_email():
    m = ReferralCreate(
        target_role=ReferralTargetRole.seller,
        invitee_name="Asha",
        invitee_phone="+919812345678",
        invitee_email="ASHA@Example.com",
        location_state="Maharashtra",
        location_area="Pune",
    )
    assert m.invitee_phone == "+919812345678"
    assert m.invitee_email == "asha@example.com"
