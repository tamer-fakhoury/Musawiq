"""Pure duplicate detection for normalized import rows."""

from __future__ import annotations


def detect_in_file_duplicates(
    normalized_rows: list[dict],
) -> dict[int, int]:
    """Map duplicate positions to the first position with the same hash.

    Rows without a dedupe hash are not compared.
    """
    first_positions: dict[str, int] = {}
    duplicates: dict[int, int] = {}

    for position, row in enumerate(normalized_rows):
        dedupe_hash = row.get("dedupe_hash")
        if not dedupe_hash:
            continue
        if dedupe_hash in first_positions:
            duplicates[position] = first_positions[dedupe_hash]
        else:
            first_positions[dedupe_hash] = position

    return duplicates


def split_against_existing(
    normalized_rows: list[dict],
    existing_hashes: set[str],
) -> tuple[list[int], list[int]]:
    """Split positions into new rows and rows matching an existing hash."""
    new_positions: list[int] = []
    duplicate_positions: list[int] = []

    for position, row in enumerate(normalized_rows):
        dedupe_hash = row.get("dedupe_hash")
        if dedupe_hash and dedupe_hash in existing_hashes:
            duplicate_positions.append(position)
        else:
            new_positions.append(position)

    return new_positions, duplicate_positions


__all__ = ["detect_in_file_duplicates", "split_against_existing"]
