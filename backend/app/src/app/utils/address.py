# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pretty single-line formatter for structured addresses."""

from app.schemas.address import AddressPayload


def format_address(addr: AddressPayload) -> str:
    parts: list[str] = [addr.address_line1]
    for optional in (addr.address_line2, addr.landmark):
        if optional and optional.strip():
            parts.append(optional.strip())
    parts.append(addr.city)
    parts.append(f"{addr.state} {addr.pincode}")
    parts.append(addr.country)
    return ", ".join(parts)
