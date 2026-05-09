# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
from app.core.indian_states import INDIAN_STATES


def test_indian_states_has_36_entries() -> None:
    assert len(INDIAN_STATES) == 36


def test_indian_states_contains_expected_names() -> None:
    assert "Maharashtra" in INDIAN_STATES
    assert "Delhi" in INDIAN_STATES
    assert "Tamil Nadu" in INDIAN_STATES
    assert "Jammu and Kashmir" in INDIAN_STATES


def test_indian_states_is_alphabetical() -> None:
    assert INDIAN_STATES == sorted(INDIAN_STATES)


def test_indian_states_are_unique() -> None:
    assert len(set(INDIAN_STATES)) == len(INDIAN_STATES)
