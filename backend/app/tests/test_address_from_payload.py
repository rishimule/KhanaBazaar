"""Tests for address_from_payload helper, focused on DIGIPIN derivation
and pass-through of new place_id / location_source fields."""
import pytest

from app.schemas.address import AddressPayload, address_from_payload


def _payload(**kwargs: object) -> AddressPayload:
    base: dict[str, object] = {
        "address_line1": "1, Main Rd",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400001",
        "country": "India",
    }
    base.update(kwargs)
    return AddressPayload(**base)


def test_no_lat_lng_yields_null_digipin() -> None:
    out = address_from_payload(_payload())
    assert out["digipin"] is None
    assert out["latitude"] is None
    assert out["longitude"] is None


def test_lat_lng_inside_india_yields_digipin() -> None:
    out = address_from_payload(_payload(latitude=18.9220, longitude=72.8347))
    assert isinstance(out["digipin"], str)
    code = out["digipin"]
    assert isinstance(code, str)
    assert len(code) == 12  # 10 chars + 2 dashes


def test_lat_lng_outside_india_yields_null_digipin_but_keeps_lat_lng() -> None:
    out = address_from_payload(_payload(
        country="UK", state="Maharashtra",  # state still validated by India rule? UK skips it
        pincode="SW1A 1AA",
        latitude=51.5074, longitude=-0.1278,
    ))
    assert out["digipin"] is None
    assert out["latitude"] == 51.5074
    assert out["longitude"] == -0.1278


def test_extra_fields_default_none() -> None:
    out = address_from_payload(_payload(latitude=18.9, longitude=72.8))
    assert out["place_id"] is None
    assert out["location_source"] is None


@pytest.mark.parametrize("source", ["manual", "autocomplete", "pin", "geocoded"])
def test_location_source_passthrough(source: str) -> None:
    out = address_from_payload(_payload(location_source=source))
    # value may be the enum instance; compare against string value
    assert getattr(out["location_source"], "value", out["location_source"]) == source


def test_place_id_passthrough() -> None:
    out = address_from_payload(_payload(place_id="ChIJabc123"))
    assert out["place_id"] == "ChIJabc123"
