# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Shared test factories."""


def make_address(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
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
