# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import pytest
from pydantic import ValidationError

from app.schemas.seller_onboarding import SellerOnboardingRequestCreate


def test_create_schema_accepts_valid_payload():
    m = SellerOnboardingRequestCreate(
        store_name="Sharma Kirana",
        contact_phone="+91 98123-45678",
        contact_email="Sharma@Example.com",
        contact_address="12 MG Road, Pune",
        preferred_categories="Grocery, Dairy",
        area_lat=18.5204,
        area_lng=73.8567,
        area_label="Pune",
        source="home",
    )
    assert m.store_name == "Sharma Kirana"


def test_create_schema_rejects_bad_email():
    with pytest.raises(ValidationError):
        SellerOnboardingRequestCreate(
            store_name="X",
            contact_phone="+919812345678",
            contact_email="not-an-email",
            contact_address="addr",
        )


def test_create_schema_rejects_empty_store_name():
    with pytest.raises(ValidationError):
        SellerOnboardingRequestCreate(
            store_name="",
            contact_phone="+919812345678",
            contact_email="a@b.com",
            contact_address="addr",
        )


def test_create_schema_rejects_overlong_address():
    with pytest.raises(ValidationError):
        SellerOnboardingRequestCreate(
            store_name="X",
            contact_phone="+919812345678",
            contact_email="a@b.com",
            contact_address="z" * 501,
        )
