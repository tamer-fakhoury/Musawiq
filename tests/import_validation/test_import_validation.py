"""Import validation orchestration contracts."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from musawiq.imports.validation import dedupe_hash, validate_row

MAPPING = {
    "product_id": "product_id",
    "product_name": "product_name",
    "order_date": "order_date",
    "quantity": "quantity",
    "sales_amount": "sales_amount",
}

CSV_HEADER = "product_id,product_name,order_date,quantity,sales_amount\n"


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _upload(client, tenant, body: bytes) -> str:
    response = client.post(
        "/imports",
        files={"file": ("sales.csv", body, "text/csv")},
        headers=_headers(tenant),
    )
    assert response.status_code == 201
    return response.json()["batch_id"]


def _attach_mapping(db_engine, tenant, batch_id: str, mapping=MAPPING) -> None:
    with db_engine.begin() as conn:
        mapping_id = conn.execute(
            text(
                """
                INSERT INTO column_mappings (
                    store_id, name, source_type, mapping, created_by
                )
                VALUES (
                    :store_id, 'test', 'csv', CAST(:mapping AS jsonb),
                    :created_by
                )
                RETURNING id
                """
            ),
            {
                "store_id": tenant.store_id,
                "mapping": json.dumps(mapping),
                "created_by": tenant.user_id,
            },
        ).scalar_one()
        conn.execute(
            text(
                "UPDATE import_batches SET column_mapping_id = :mapping_id "
                "WHERE id = :batch_id"
            ),
            {"mapping_id": mapping_id, "batch_id": uuid.UUID(batch_id)},
        )


def _validate(client, tenant, batch_id: str):
    return client.post(
        f"/imports/{batch_id}/validate",
        headers=_headers(tenant),
    )


def test_clean_file_is_all_valid_and_preview(
    client, tenant, db_engine
) -> None:
    body = CSV_HEADER + "p1,Shirt,2026-01-01,2,49.90\np2,Hat,2026-01-02,1,20.00\n"
    batch_id = _upload(client, tenant, body.encode())
    _attach_mapping(db_engine, tenant, batch_id)

    response = _validate(client, tenant, batch_id)

    assert response.status_code == 200
    assert response.json() == {
        "batch_id": batch_id,
        "status": "preview",
        "counts": {"total": 2, "valid": 2, "invalid": 0, "duplicate": 0},
    }

    with db_engine.connect() as conn:
        batch = conn.execute(
            text(
                "SELECT status, total_rows, valid_rows, invalid_rows, "
                "duplicate_rows FROM import_batches WHERE id = :id"
            ),
            {"id": uuid.UUID(batch_id)},
        ).mappings().one()
        rows = conn.execute(
            text(
                "SELECT row_number, status, issue_count FROM import_rows "
                "WHERE import_batch_id = :id ORDER BY row_number"
            ),
            {"id": uuid.UUID(batch_id)},
        ).mappings().all()
        issues = conn.execute(
            text(
                "SELECT count(*) FROM import_issues "
                "WHERE import_batch_id = :id"
            ),
            {"id": uuid.UUID(batch_id)},
        ).scalar_one()

    assert batch["status"] == "preview"
    assert batch["total_rows"] == 2
    assert batch["valid_rows"] == 2
    assert batch["invalid_rows"] == 0
    assert batch["duplicate_rows"] == 0
    assert [row["status"] for row in rows] == ["valid", "valid"]
    assert [row["issue_count"] for row in rows] == [0, 0]
    assert issues == 0


def test_bad_date_and_zero_quantity_are_invalid(
    client, tenant, db_engine
) -> None:
    body = (
        CSV_HEADER
        + "p1,Shirt,not-a-date,1,10.00\n"
        + "p2,Hat,2026-01-01,0,20.00\n"
    )
    batch_id = _upload(client, tenant, body.encode())
    _attach_mapping(db_engine, tenant, batch_id)

    response = _validate(client, tenant, batch_id)

    assert response.status_code == 200
    assert response.json()["counts"] == {
        "total": 2,
        "valid": 0,
        "invalid": 2,
        "duplicate": 0,
    }

    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT row_number, status, issue_count FROM import_rows "
                "WHERE import_batch_id = :id ORDER BY row_number"
            ),
            {"id": uuid.UUID(batch_id)},
        ).mappings().all()
        issues = conn.execute(
            text(
                "SELECT row_number, issue_code FROM import_issues "
                "WHERE import_batch_id = :id ORDER BY row_number"
            ),
            {"id": uuid.UUID(batch_id)},
        ).mappings().all()

    assert [row["status"] for row in rows] == ["invalid", "invalid"]
    assert [row["issue_count"] for row in rows] == [1, 1]
    assert {(issue["row_number"], issue["issue_code"]) for issue in issues} == {
        (1, "invalid_date"),
        (2, "invalid_quantity"),
    }


def test_in_file_duplicate_is_flagged(client, tenant, db_engine) -> None:
    body = CSV_HEADER + "p1,Shirt,2026-01-01,2,49.90\n" * 2
    batch_id = _upload(client, tenant, body.encode())
    _attach_mapping(db_engine, tenant, batch_id)

    response = _validate(client, tenant, batch_id)

    assert response.status_code == 200
    assert response.json()["counts"] == {
        "total": 2,
        "valid": 1,
        "invalid": 0,
        "duplicate": 1,
    }

    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT row_number, status FROM import_rows "
                "WHERE import_batch_id = :id ORDER BY row_number"
            ),
            {"id": uuid.UUID(batch_id)},
        ).mappings().all()
        issue = conn.execute(
            text(
                "SELECT issue_code FROM import_issues "
                "WHERE import_batch_id = :id"
            ),
            {"id": uuid.UUID(batch_id)},
        ).mappings().one()

    assert [(row["row_number"], row["status"]) for row in rows] == [
        (1, "valid"),
        (2, "duplicate"),
    ]
    assert issue["issue_code"] == "duplicate_in_file"


def test_existing_order_hash_is_flagged(client, tenant, db_engine) -> None:
    raw = {
        "product_id": "p1",
        "product_name": "Shirt",
        "order_date": "2026-01-01",
        "quantity": "2",
        "sales_amount": "49.90",
    }
    normalized, issues = validate_row(
        raw, MAPPING, timezone="UTC", default_currency="USD"
    )
    assert issues == []
    existing_hash = dedupe_hash(normalized)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO orders (
                    store_id, origin, status, currency, placed_at, dedupe_hash
                )
                VALUES (
                    :store_id, 'imported', 'pending', 'USD', now(), :dedupe_hash
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "dedupe_hash": existing_hash,
            },
        )

    body = CSV_HEADER + "p1,Shirt,2026-01-01,2,49.90\n"
    batch_id = _upload(client, tenant, body.encode())
    _attach_mapping(db_engine, tenant, batch_id)

    response = _validate(client, tenant, batch_id)

    assert response.status_code == 200
    assert response.json()["counts"] == {
        "total": 1,
        "valid": 0,
        "invalid": 0,
        "duplicate": 1,
    }

    with db_engine.connect() as conn:
        status = conn.execute(
            text(
                "SELECT status FROM import_rows "
                "WHERE import_batch_id = :id"
            ),
            {"id": uuid.UUID(batch_id)},
        ).scalar_one()
        issue_code = conn.execute(
            text(
                "SELECT issue_code FROM import_issues "
                "WHERE import_batch_id = :id"
            ),
            {"id": uuid.UUID(batch_id)},
        ).scalar_one()

    assert status == "duplicate"
    assert issue_code == "duplicate_existing"


def test_missing_mapping_returns_409(client, tenant) -> None:
    body = CSV_HEADER + "p1,Shirt,2026-01-01,2,49.90\n"
    batch_id = _upload(client, tenant, body.encode())

    response = _validate(client, tenant, batch_id)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "mapping_required"
    assert error["correlation_id"] == response.headers["X-Correlation-ID"]


def test_second_validation_replaces_results(
    client, tenant, db_engine
) -> None:
    body = (
        CSV_HEADER
        + "p1,Shirt,2026-01-01,1,10.00\n"
        + "p2,Hat,not-a-date,1,20.00\n"
    )
    batch_id = _upload(client, tenant, body.encode())
    _attach_mapping(db_engine, tenant, batch_id)

    first = _validate(client, tenant, batch_id)
    second = _validate(client, tenant, batch_id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["counts"] == {
        "total": 2,
        "valid": 1,
        "invalid": 1,
        "duplicate": 0,
    }

    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT count(*) FROM import_rows "
                "WHERE import_batch_id = :id"
            ),
            {"id": uuid.UUID(batch_id)},
        ).scalar_one()
        issues = conn.execute(
            text(
                "SELECT count(*) FROM import_issues "
                "WHERE import_batch_id = :id"
            ),
            {"id": uuid.UUID(batch_id)},
        ).scalar_one()

    assert rows == 2
    assert issues == 1
