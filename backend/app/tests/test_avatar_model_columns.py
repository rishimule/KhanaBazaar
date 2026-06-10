# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
from app.models.profile import CustomerProfile, SellerProfile
from app.models.seller_profile_change_request import SellerProfileChangeGroup


def test_profiles_have_avatar_columns():
    assert "avatar_url" in CustomerProfile.model_fields
    assert "avatar_storage_key" in CustomerProfile.model_fields
    assert "avatar_url" in SellerProfile.model_fields
    assert "avatar_storage_key" in SellerProfile.model_fields


def test_change_group_has_avatar():
    assert SellerProfileChangeGroup.Avatar.value == "avatar"
