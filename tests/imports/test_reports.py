"""Import preview counts and error-report CSV."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from musawiq.imports.reports import error_report_csv, summarize
from musawiq.imports.validation import Issue


@dataclass(frozen=True)
class RowIssue(Issue):
    row_number: int = 0


def test_summary_shape_and_consistency() -> None:
    assert summarize(10, 6, 3, 1) == {
        "total": 10,
        "valid": 6,
        "invalid": 3,
        "duplicate": 1,
    }

    with pytest.raises(ValueError, match="exceed"):
        summarize(2, 2, 1, 0)


def test_csv_has_header_and_one_issue_row() -> None:
    issue = RowIssue(
        field="quantity",
        code="invalid_quantity",
        message="must be positive, integer",
        raw_value="0",
        row_number=7,
    )

    data = error_report_csv([issue])

    assert not data.startswith(b"\xef\xbb\xbf")
    assert data.decode("utf-8").splitlines() == [
        "row_number,field,code,message,raw_value",
        '7,quantity,invalid_quantity,"must be positive, integer",0',
    ]


def test_empty_issue_list_returns_header_only() -> None:
    assert error_report_csv([]) == (
        b"row_number,field,code,message,raw_value\n"
    )
