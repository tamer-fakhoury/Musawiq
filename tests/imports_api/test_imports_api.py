"""Import upload, template, history, and batch fetch contracts."""

from __future__ import annotations

import uuid

from sqlalchemy import text


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def test_upload_creates_batch_and_staged_file(
    client, tenant, db_engine
) -> None:
    content = b"product_id,product_name\np1,Shirt\n"

    response = client.post(
        "/imports",
        files={"file": ("sales.csv", content, "text/csv")},
        data={"strict_mode": "true"},
        headers=_headers(tenant),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "uploaded"
    assert body["file"]["size_bytes"] == len(content)
    assert len(body["file"]["checksum_sha256"]) == 64

    with db_engine.connect() as conn:
        batch = conn.execute(
            text(
                "SELECT store_id, source_type, stored_file_id, status, "
                "strict_mode, total_rows, valid_rows, invalid_rows, "
                "duplicate_rows, created_by FROM import_batches "
                "WHERE id = :id"
            ),
            {"id": uuid.UUID(body["batch_id"])},
        ).mappings().one()
        stored = conn.execute(
            text(
                "SELECT purpose, status, size_bytes, checksum_sha256, "
                "mime_type, uploaded_by_user_id FROM stored_files "
                "WHERE id = :id"
            ),
            {"id": batch["stored_file_id"]},
        ).mappings().one()
        products = conn.execute(
            text("SELECT count(*) FROM products WHERE store_id = :store_id"),
            {"store_id": tenant.store_id},
        ).scalar_one()
        orders = conn.execute(
            text("SELECT count(*) FROM orders WHERE store_id = :store_id"),
            {"store_id": tenant.store_id},
        ).scalar_one()

    assert batch["store_id"] == tenant.store_id
    assert batch["source_type"] == "csv"
    assert batch["status"] == "uploaded"
    assert batch["strict_mode"] is True
    assert batch["total_rows"] == 0
    assert batch["valid_rows"] == 0
    assert batch["invalid_rows"] == 0
    assert batch["duplicate_rows"] == 0
    assert batch["created_by"] == tenant.user_id
    assert stored["purpose"] == "sales_csv"
    assert stored["status"] == "staged"
    assert stored["size_bytes"] == len(content)
    assert stored["mime_type"] == "text/csv"
    assert stored["uploaded_by_user_id"] == tenant.user_id
    assert products == 0
    assert orders == 0


def test_non_csv_is_rejected(client, tenant) -> None:
    response = client.post(
        "/imports",
        files={"file": ("sales.txt", b"a,b\n1,2\n", "text/csv")},
        headers=_headers(tenant),
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_file_type"
    assert error["correlation_id"] == response.headers["X-Correlation-ID"]


def test_empty_file_is_rejected(client, tenant) -> None:
    response = client.post(
        "/imports",
        files={"file": ("empty.csv", b"", "text/csv")},
        headers=_headers(tenant),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_file"


def test_template_downloads_with_header_row(client, tenant) -> None:
    response = client.get("/imports/template.csv", headers=_headers(tenant))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"].lower()
    assert response.text.splitlines()[0] == (
        "product_id,product_name,order_date,quantity,sales_amount,"
        "order_id,currency,sku"
    )


def test_history_is_scoped_to_the_caller_store(
    client, tenant, make_tenant
) -> None:
    other = make_tenant()
    created = client.post(
        "/imports",
        files={"file": ("sales.csv", b"product_id\np1\n", "text/csv")},
        headers=_headers(tenant),
    )
    batch_id = created.json()["batch_id"]

    own = client.get("/imports", headers=_headers(tenant))
    other_history = client.get("/imports", headers=_headers(other))

    assert own.status_code == 200
    assert len(own.json()) == 1
    assert own.json()[0]["id"] == batch_id
    assert set(own.json()[0]) == {
        "id",
        "status",
        "total_rows",
        "valid_rows",
        "invalid_rows",
        "duplicate_rows",
        "created_at",
    }
    assert other_history.status_code == 200
    assert other_history.json() == []


def test_batch_fetch_returns_uploaded_state_and_404_for_other_store(
    client, tenant, make_tenant
) -> None:
    other = make_tenant()
    created = client.post(
        "/imports",
        files={"file": ("sales.csv", b"product_id\np1\n", "text/csv")},
        headers=_headers(tenant),
    )
    batch_id = created.json()["batch_id"]

    own = client.get(f"/imports/{batch_id}", headers=_headers(tenant))
    forbidden = client.get(f"/imports/{batch_id}", headers=_headers(other))

    assert own.status_code == 200
    assert own.json()["id"] == batch_id
    assert own.json()["status"] == "uploaded"
    assert own.json()["total_rows"] == 0

    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "not_found"
