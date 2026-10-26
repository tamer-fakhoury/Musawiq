"""Preview counts and downloadable import error reports."""

from __future__ import annotations

import csv
import io

from musawiq.imports.validation import Issue

CSV_HEADER = ("row_number", "field", "code", "message", "raw_value")


def summarize(
    total: int,
    valid: int,
    invalid: int,
    duplicate: int,
) -> dict[str, int]:
    counts = {
        "total": total,
        "valid": valid,
        "invalid": invalid,
        "duplicate": duplicate,
    }
    if any(value < 0 for value in counts.values()):
        raise ValueError("import counts must not be negative")
    if valid + invalid + duplicate > total:
        raise ValueError("import categories exceed the total row count")
    return counts


def error_report_csv(issues: list[Issue]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for issue in issues:
        row_number = getattr(issue, "row_number", "")
        writer.writerow(
            [
                "" if row_number is None else row_number,
                issue.field,
                issue.code,
                issue.message,
                issue.raw_value,
            ]
        )
    return buffer.getvalue().encode("utf-8")


__all__ = ["CSV_HEADER", "error_report_csv", "summarize"]
