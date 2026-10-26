"""Import preview and error-report API."""

from __future__ import annotations

from typing import Any


def _headers(seed: Any) -> dict[str, str]:
    return {
        "X-Store-Id": str(seed.store_id),
        "X-User-Id": str(seed.user_id),
        "X-User-Role": "owner",
    }


def test_preview_counts_rows_and_paginated_issues(client, seed) -> None:
    response = client.get(
        f"/imports/{seed.preview_batch}/preview",
        headers=_headers(seed),
        params={"limit": 2, "offset": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["counts"] == {
        "total": 4,
        "valid": 2,
        "invalid": 1,
        "duplicate": 1,
    }
    assert body["rows"] == [
        {"row_number": 1, "status": "valid"},
        {"row_number": 2, "status": "valid"},
    ]
    assert body["issues"]["total"] == 3
    assert body["issues"]["limit"] == 2
    assert body["issues"]["offset"] == 0
    assert len(body["issues"]["items"]) == 2

    second = client.get(
        f"/imports/{seed.preview_batch}/preview",
        headers=_headers(seed),
        params={"limit": 2, "offset": 2},
    )
    assert second.status_code == 200
    assert second.json()["rows"] == body["rows"]
    assert second.json()["issues"]["offset"] == 2
    assert len(second.json()["issues"]["items"]) == 1


def test_preview_before_validation_returns_409(client, seed) -> None:
    response = client.get(
        f"/imports/{seed.not_validated_batch}/preview",
        headers=_headers(seed),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_validated"


def test_preview_from_another_store_returns_404(client, seed) -> None:
    response = client.get(
        f"/imports/{seed.other_batch}/preview",
        headers=_headers(seed),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_error_report_csv_has_header_and_issue_row(client, seed) -> None:
    response = client.get(
        f"/imports/{seed.csv_batch}/error-report.csv",
        headers=_headers(seed),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="import-{seed.csv_batch}-errors.csv"'
    )
    assert response.text.splitlines() == [
        "row_number,field,code,message,raw_value",
        '7,sales_amount,invalid_amount,"must be non-negative, decimal",-1',
    ]


def test_empty_error_report_is_header_only(client, seed) -> None:
    response = client.get(
        f"/imports/{seed.empty_batch}/error-report.csv",
        headers=_headers(seed),
    )

    assert response.status_code == 200
    assert response.text == "row_number,field,code,message,raw_value\n"
