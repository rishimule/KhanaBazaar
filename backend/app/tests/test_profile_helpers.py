# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from app.services.profiles import compose_full_name, split_full_name


def test_split_full_name_splits_first_token_and_rest() -> None:
    assert split_full_name("Priya Verma") == ("Priya", "Verma")
    assert split_full_name("Ravi") == ("Ravi", None)
    assert split_full_name("  Sana   Kapoor  ") == ("Sana", "Kapoor")


def test_compose_full_name_skips_missing_last_name() -> None:
    assert compose_full_name("Priya", "Verma") == "Priya Verma"
    assert compose_full_name("Ravi", None) == "Ravi"
