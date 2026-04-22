import pytest
from pydantic import ValidationError

from app.schemas.address import AddressPayload


def _valid_dict(**overrides: object) -> dict:
    base = {
        "address_line1": "12 MG Road",
        "address_line2": "Sector 14",
        "landmark": "Near Cyber Hub",
        "city": "Gurugram",
        "state": "Haryana",
        "pincode": "122001",
        "country": "India",
        "latitude": 28.4595,
        "longitude": 77.0266,
    }
    base.update(overrides)
    return base


def test_valid_address_passes() -> None:
    addr = AddressPayload(**_valid_dict())
    assert addr.pincode == "122001"


def test_optional_fields_accept_none() -> None:
    addr = AddressPayload(
        **_valid_dict(address_line2=None, landmark=None, latitude=None, longitude=None)
    )
    assert addr.address_line2 is None
    assert addr.landmark is None
    assert addr.latitude is None
    assert addr.longitude is None


def test_india_pincode_leading_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(pincode="023456"))


def test_india_pincode_five_digits_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(pincode="12345"))


def test_india_pincode_non_numeric_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(pincode="abcdef"))


def test_non_india_country_accepts_other_postal_format() -> None:
    addr = AddressPayload(
        **_valid_dict(country="Nepal", state="Bagmati", pincode="44600")
    )
    assert addr.country == "Nepal"


def test_india_state_not_in_list_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(state="Atlantis"))


def test_non_india_state_free_text_accepted() -> None:
    addr = AddressPayload(
        **_valid_dict(country="Nepal", state="Bagmati", pincode="44600")
    )
    assert addr.state == "Bagmati"


def test_latitude_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(latitude=91.0))


def test_longitude_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(longitude=-181.0))


def test_required_field_missing_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(address_line1=""))


def test_address_line1_max_length_enforced() -> None:
    with pytest.raises(ValidationError):
        AddressPayload(**_valid_dict(address_line1="x" * 121))
