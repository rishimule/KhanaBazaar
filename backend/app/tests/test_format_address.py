from app.schemas.address import AddressPayload
from app.utils.address import format_address


def _payload(**overrides: object) -> AddressPayload:
    base: dict[str, object] = {
        "address_line1": "12 MG Road",
        "address_line2": "Sector 14",
        "landmark": "Near Cyber Hub",
        "city": "Gurugram",
        "state": "Haryana",
        "pincode": "122001",
        "country": "India",
        "latitude": None,
        "longitude": None,
    }
    base.update(overrides)
    return AddressPayload(**base)


def test_format_full_address() -> None:
    assert format_address(_payload()) == (
        "12 MG Road, Sector 14, Near Cyber Hub, Gurugram, Haryana 122001, India"
    )


def test_format_without_optional_parts() -> None:
    assert format_address(_payload(address_line2=None, landmark=None)) == (
        "12 MG Road, Gurugram, Haryana 122001, India"
    )


def test_format_strips_empty_optional_strings() -> None:
    assert format_address(_payload(address_line2="", landmark="   ")) == (
        "12 MG Road, Gurugram, Haryana 122001, India"
    )
