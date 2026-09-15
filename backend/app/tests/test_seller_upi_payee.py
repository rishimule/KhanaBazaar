# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"""Seller UPI payee: model columns, CR group, payload validation, QR storage
helper, and the change-request apply flow.

Mirrors the store-logo suite (test_store_logo.py). Uses the local
image-storage backend against tmp_path so no GCS/network is touched."""
import pytest
from pydantic import ValidationError

from app.models.commerce import Payment
from app.models.profile import SellerProfile
from app.models.seller_profile_change_request import SellerProfileChangeGroup
from app.schemas.seller_profile_change_request import validate_group_payload


def test_seller_profile_has_upi_columns() -> None:
    assert {
        "upi_vpa",
        "upi_qr_url",
        "upi_qr_storage_key",
        "upi_enabled",
    } <= set(SellerProfile.model_fields.keys())


def test_upi_enabled_defaults_false() -> None:
    assert SellerProfile.model_fields["upi_enabled"].default is False


def test_payment_has_customer_claimed_at() -> None:
    assert "customer_claimed_at" in Payment.model_fields


def test_payments_group_value() -> None:
    assert SellerProfileChangeGroup.Payments.value == "payments"


# ── C2: VPA payload validation ────────────────────────────────────────
@pytest.mark.parametrize(
    "vpa",
    ["name@okhdfcbank", "9876543210@paytm", "a.b-c_d@ybl", "x2@sbi"],
)
def test_valid_vpas_accepted(vpa: str) -> None:
    out = validate_group_payload(
        SellerProfileChangeGroup.Payments, {"upi_vpa": vpa, "upi_enabled": True}
    )
    assert out["upi_vpa"] == vpa
    assert out["upi_enabled"] is True


@pytest.mark.parametrize(
    "vpa",
    [
        "nobank",            # no @
        "@okhdfcbank",       # empty handle
        "name@",             # empty bank
        "name@1bank",        # bank must start with a letter
        "a@ybl",             # handle shorter than 2 chars
        "name@@ybl",         # double @
        "na me@ybl",         # whitespace
    ],
)
def test_invalid_vpas_rejected(vpa: str) -> None:
    with pytest.raises(ValidationError):
        validate_group_payload(
            SellerProfileChangeGroup.Payments, {"upi_vpa": vpa}
        )


def test_enabled_without_vpa_rejected() -> None:
    """The core invariant: UPI cannot be on with no payee to pay."""
    with pytest.raises(ValidationError):
        validate_group_payload(
            SellerProfileChangeGroup.Payments,
            {"upi_vpa": None, "upi_enabled": True},
        )


def test_payments_removal_payload() -> None:
    out = validate_group_payload(
        SellerProfileChangeGroup.Payments, {"upi_vpa": "", "upi_enabled": False}
    )
    assert out["upi_vpa"] is None
    assert out["upi_enabled"] is False
    assert out["upi_qr_url"] == ""
    assert out["storage_key"] is None
