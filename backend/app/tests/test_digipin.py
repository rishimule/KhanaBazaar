"""Tests for India Post DIGIPIN encode/decode (10-char alphanumeric grid code).

Reference algorithm: India Post / IIT-Hyderabad. Bounds: lat 2.5-38.5, lng 63.5-99.5.

These tests cover format, bounds, and round-trip — all properties derivable
from the published algorithm without needing the official reference encoder.
Landmark-vs-reference verification is deferred to a separate manual QA pass.
"""
import pytest

from app.utils.digipin import decode, encode

_INDIA_LANDMARKS: list[tuple[str, float, float]] = [
    ("India Gate, New Delhi", 28.6129, 77.2295),
    ("Gateway of India, Mumbai", 18.9220, 72.8347),
    ("Charminar, Hyderabad", 17.3616, 78.4747),
    ("Mysore Palace", 12.3052, 76.6552),
    ("Howrah Bridge, Kolkata", 22.5851, 88.3468),
]


def test_encode_returns_10_chars_in_xxx_xxx_xxxx_format() -> None:
    code = encode(28.6129, 77.2295)
    assert len(code) == 12
    assert code[3] == "-"
    assert code[7] == "-"
    cleaned = code.replace("-", "")
    assert len(cleaned) == 10


@pytest.mark.parametrize("name,lat,lng", _INDIA_LANDMARKS)
def test_encode_all_chars_valid(name: str, lat: float, lng: float) -> None:
    valid = set("FCJ8K9L23M456P7T")
    code = encode(lat, lng).replace("-", "")
    assert set(code).issubset(valid), f"{name}: {code}"


@pytest.mark.parametrize(
    "lat,lng",
    [
        (0.0, 75.0),     # below min lat
        (40.0, 75.0),    # above max lat
        (20.0, 60.0),    # below min lng
        (20.0, 100.0),   # above max lng
        (-10.0, 75.0),   # negative lat
        (20.0, -75.0),   # negative lng
    ],
)
def test_encode_rejects_out_of_bounds(lat: float, lng: float) -> None:
    with pytest.raises(ValueError):
        encode(lat, lng)


@pytest.mark.parametrize("name,lat,lng", _INDIA_LANDMARKS)
def test_decode_round_trip_within_cell_precision(
    name: str, lat: float, lng: float,
) -> None:
    code = encode(lat, lng)
    out_lat, out_lng = decode(code)
    # Level-10 cell precision is ~3.8m. The decoded centre must lie within
    # one cell of the original point (~ 1 cell diagonal in degrees).
    cell_lat_step = (38.5 - 2.5) / (4 ** 10)
    cell_lng_step = (99.5 - 63.5) / (4 ** 10)
    assert abs(out_lat - lat) < cell_lat_step, f"{name}: lat drift {out_lat - lat}"
    assert abs(out_lng - lng) < cell_lng_step, f"{name}: lng drift {out_lng - lng}"


def test_decode_accepts_lowercase() -> None:
    code = encode(28.6129, 77.2295)
    upper = decode(code)
    lower = decode(code.lower())
    assert upper == lower


def test_decode_accepts_no_dashes() -> None:
    code = encode(28.6129, 77.2295)
    a = decode(code)
    b = decode(code.replace("-", ""))
    assert a == b


def test_decode_invalid_chars_rejected() -> None:
    with pytest.raises(ValueError):
        decode("ZZZ-ZZZ-ZZZZ")


def test_decode_wrong_length_rejected() -> None:
    with pytest.raises(ValueError):
        decode("ABC")
    with pytest.raises(ValueError):
        decode("FCJK4M-5P-T7L9")
