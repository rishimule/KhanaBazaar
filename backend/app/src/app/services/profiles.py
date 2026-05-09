# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from typing import Optional


def split_full_name(full_name: str) -> tuple[str, Optional[str]]:
    parts = " ".join(full_name.strip().split()).split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) == 2 else None
    return first_name, last_name


def compose_full_name(first_name: str, last_name: Optional[str]) -> str:
    if last_name:
        return f"{first_name} {last_name}"
    return first_name
