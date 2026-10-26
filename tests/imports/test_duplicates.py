"""Duplicate detection contracts."""

from __future__ import annotations

from musawiq.imports.duplicates import (
    detect_in_file_duplicates,
    split_against_existing,
)


def test_in_file_duplicate_found() -> None:
    rows = [
        {"dedupe_hash": "a"},
        {"dedupe_hash": "b"},
        {"dedupe_hash": "a"},
        {"dedupe_hash": "c"},
        {"dedupe_hash": "b"},
    ]

    assert detect_in_file_duplicates(rows) == {2: 0, 4: 1}


def test_unique_rows_untouched() -> None:
    rows = [
        {"dedupe_hash": "a"},
        {"dedupe_hash": "b"},
        {"dedupe_hash": "c"},
    ]

    assert detect_in_file_duplicates(rows) == {}
    assert split_against_existing(rows, set()) == ([0, 1, 2], [])


def test_existing_hash_match_flagged() -> None:
    rows = [
        {"dedupe_hash": "a"},
        {"dedupe_hash": "b"},
        {"dedupe_hash": "c"},
    ]

    assert split_against_existing(rows, {"a", "c"}) == ([1], [0, 2])


def test_empty_input_returns_empty() -> None:
    assert detect_in_file_duplicates([]) == {}
    assert split_against_existing([], {"a"}) == ([], [])
