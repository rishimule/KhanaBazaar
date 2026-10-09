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


def signup_phone_token(email: str, phone: str = "+919800000001") -> str:
    """A phone token as POST /auth/customer/phone/otp/* would mint it, for
    tests that create a customer through /auth/otp/verify or
    /referrals/accept. Give each customer in a test its own number — the
    customer phone column is unique."""
    from app.core.security import create_customer_signup_phone_token

    return create_customer_signup_phone_token(
        email.strip().lower(), phone, proven=True
    )
