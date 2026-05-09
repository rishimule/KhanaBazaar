# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""India Post DIGIPIN encode/decode.

Open algorithm published by India Post / IIT-Hyderabad. Encodes a lat/lng
inside the India bounding box (2.5-38.5 lat, 63.5-99.5 lng) into a 10-char
alphanumeric grid code rendered as `XXX-XXX-XXXX`. Each character narrows
the cell by a factor of 4x4 (16 cells per level, 10 levels deep, ~3.8m
final precision).
"""
from __future__ import annotations

# 4x4 character matrix as published by India Post.
_GRID: tuple[tuple[str, ...], ...] = (
    ("F", "C", "9", "8"),
    ("J", "3", "2", "7"),
    ("K", "4", "5", "6"),
    ("L", "M", "P", "T"),
)

_LAT_MIN, _LAT_MAX = 2.5, 38.5
_LNG_MIN, _LNG_MAX = 63.5, 99.5
_LEVELS = 10

_CHAR_TO_RC: dict[str, tuple[int, int]] = {
    ch: (r, c)
    for r, row in enumerate(_GRID)
    for c, ch in enumerate(row)
}


def _flatten(code: str) -> str:
    return code.replace("-", "")


def encode(lat: float, lng: float) -> str:
    """Return the DIGIPIN for a lat/lng inside the India bounding box.

    Raises:
        ValueError: lat or lng outside the India bbox.
    """
    if not (_LAT_MIN <= lat <= _LAT_MAX):
        raise ValueError(f"latitude {lat} outside India bbox [{_LAT_MIN}, {_LAT_MAX}]")
    if not (_LNG_MIN <= lng <= _LNG_MAX):
        raise ValueError(f"longitude {lng} outside India bbox [{_LNG_MIN}, {_LNG_MAX}]")

    lat_lo, lat_hi = _LAT_MIN, _LAT_MAX
    lng_lo, lng_hi = _LNG_MIN, _LNG_MAX
    chars: list[str] = []

    for _ in range(_LEVELS):
        lat_step = (lat_hi - lat_lo) / 4.0
        lng_step = (lng_hi - lng_lo) / 4.0
        # Row 0 of the grid is the TOP (highest latitude).
        row = 3 - min(int((lat - lat_lo) / lat_step), 3)
        col = min(int((lng - lng_lo) / lng_step), 3)
        chars.append(_GRID[row][col])

        new_lat_hi = lat_hi - row * lat_step
        new_lat_lo = lat_hi - (row + 1) * lat_step
        new_lng_lo = lng_lo + col * lng_step
        new_lng_hi = lng_lo + (col + 1) * lng_step
        lat_lo, lat_hi = new_lat_lo, new_lat_hi
        lng_lo, lng_hi = new_lng_lo, new_lng_hi

    raw = "".join(chars)
    return f"{raw[:3]}-{raw[3:6]}-{raw[6:]}"


def decode(code: str) -> tuple[float, float]:
    """Return the lat/lng of the cell centre for a DIGIPIN.

    Raises:
        ValueError: code is the wrong length or contains invalid characters.
    """
    raw = _flatten(code).upper()
    if len(raw) != _LEVELS:
        raise ValueError(f"DIGIPIN must be {_LEVELS} chars excluding dashes")

    lat_lo, lat_hi = _LAT_MIN, _LAT_MAX
    lng_lo, lng_hi = _LNG_MIN, _LNG_MAX

    for ch in raw:
        if ch not in _CHAR_TO_RC:
            raise ValueError(f"invalid DIGIPIN char {ch!r}")
        row, col = _CHAR_TO_RC[ch]
        lat_step = (lat_hi - lat_lo) / 4.0
        lng_step = (lng_hi - lng_lo) / 4.0
        new_lat_hi = lat_hi - row * lat_step
        new_lat_lo = lat_hi - (row + 1) * lat_step
        new_lng_lo = lng_lo + col * lng_step
        new_lng_hi = lng_lo + (col + 1) * lng_step
        lat_lo, lat_hi = new_lat_lo, new_lat_hi
        lng_lo, lng_hi = new_lng_lo, new_lng_hi

    return (lat_lo + lat_hi) / 2.0, (lng_lo + lng_hi) / 2.0
