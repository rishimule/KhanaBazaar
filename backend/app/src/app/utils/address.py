# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Pretty single-line formatter for structured addresses."""

from typing import Optional, Protocol


class AddressLike(Protocol):
    """Anything with the address fields: an AddressPayload or an Address row.
    Taking a row directly skips AddressPayload's country validators, so a
    legacy address that predates them still formats (receipts must not fail)."""

    @property
    def address_line1(self) -> str: ...
    @property
    def address_line2(self) -> Optional[str]: ...
    @property
    def landmark(self) -> Optional[str]: ...
    @property
    def city(self) -> str: ...
    @property
    def state(self) -> str: ...
    @property
    def pincode(self) -> str: ...
    @property
    def country(self) -> str: ...


def format_address(addr: AddressLike) -> str:
    parts: list[str] = [addr.address_line1]
    for optional in (addr.address_line2, addr.landmark):
        if optional and optional.strip():
            parts.append(optional.strip())
    parts.append(addr.city)
    parts.append(f"{addr.state} {addr.pincode}")
    parts.append(addr.country)
    return ", ".join(parts)
