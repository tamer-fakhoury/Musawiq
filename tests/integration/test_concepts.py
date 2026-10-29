"""FR-2.1.1 product concept creation and draft editing."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from musawiq.services import concepts as concept_service

PNG_BYTES = b"\x89PNG\r\n\x1a\nconcept-image"


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _payload(taxonomy, **overrides):
    category_id, niche_id = taxonomy
    payload = {
        "name": "Travel mug",
        "description": "Insulated stainless steel travel mug",
        "category_id": str(category_id),
        "niche_id": str(niche_id),
        "price_minor": 1000,
        "cost_minor": 400,
        "currency": "usd",
    }
    payload.update(overrides)
    return payload


def _create(client, tenant, taxonomy, **overrides):
    return client.post(
        "/product-concepts",
        json=_payload(taxonomy, **overrides),
        headers=_headers(tenant),
    )


def test_create_draft_concept_computes_margin_and_records_creator(
    client, tenant, taxonomy, db_engine
) -> None:
    response = _create(client, tenant, taxonomy)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Travel mug"
    assert body["description"] == "Insulated stainless steel travel mug"
    assert body["status"] == "draft"
    assert body["version"] == 1
    assert body["currency"] == "USD"
    assert body["gross_margin_bp"] == 6000
    assert body["gross_margin_percent"] == 60.0
    assert body["is_negative_margin"] is False
    assert body["created_by"] == str(tenant.user_id)

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT store_id, status, version, gross_margin_bp, created_by
                FROM product_concepts WHERE id = :id
                """
            ),
            {"id": uuid.UUID(body["id"])},
        ).mappings().one()
    assert row["store_id"] == tenant.store_id
    assert row["status"] == "draft"
    assert row["version"] == 1
    assert row["gross_margin_bp"] == 6000
    assert row["created_by"] == tenant.user_id

    reloaded = client.get(
        f"/product-concepts/{body['id']}", headers=_headers(tenant)
    )
    assert reloaded.status_code == 200
    assert reloaded.json()["id"] == body["id"]
    assert reloaded.json()["gross_margin_bp"] == 6000


def test_negative_margin_is_flagged(client, tenant, taxonomy) -> None:
    response = _create(client, tenant, taxonomy, price_minor=500, cost_minor=700)

    assert response.status_code == 201
    body = response.json()
    assert body["gross_margin_bp"] == -4000
    assert body["gross_margin_percent"] == -40.0
    assert body["is_negative_margin"] is True


def test_required_field_errors_are_field_level(
    client, tenant, db_engine
) -> None:
    response = client.post(
        "/product-concepts",
        json={
            "name": " ",
            "description": "",
            "category_id": "not-a-uuid",
            "price_minor": 0,
            "cost_minor": -1,
            "currency": "US",
        },
        headers=_headers(tenant),
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["correlation_id"] == response.headers["X-Correlation-ID"]
    assert set(error["fields"]) >= {
        "name",
        "description",
        "category_id",
        "price_minor",
        "cost_minor",
        "currency",
    }

    with db_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM product_concepts WHERE store_id = :store_id"
            ),
            {"store_id": tenant.store_id},
        ).scalar_one()
    assert count == 0


def test_product_image_is_stored_and_linked(
    client, tenant, taxonomy, db_engine
) -> None:
    category_id, niche_id = taxonomy
    response = client.post(
        "/product-concepts",
        data={
            "name": "Travel mug",
            "description": "Insulated stainless steel travel mug",
            "category_id": str(category_id),
            "niche_id": str(niche_id),
            "price_minor": "1000",
            "cost_minor": "400",
            "currency": "USD",
        },
        files={"image": ("mug.png", PNG_BYTES, "image/png")},
        headers=_headers(tenant),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["image_file_id"] is not None

    with db_engine.connect() as conn:
        stored = conn.execute(
            text(
                """
                SELECT purpose, status, mime_type, size_bytes, uploaded_by_user_id
                FROM stored_files WHERE id = :id
                """
            ),
            {"id": uuid.UUID(body["image_file_id"])},
        ).mappings().one()
        concept = conn.execute(
            text("SELECT image_file_id FROM product_concepts WHERE id = :id"),
            {"id": uuid.UUID(body["id"])},
        ).mappings().one()

    assert stored["purpose"] == "product_image"
    assert stored["status"] == "committed"
    assert stored["mime_type"] == "image/png"
    assert stored["size_bytes"] == len(PNG_BYTES)
    assert stored["uploaded_by_user_id"] == tenant.user_id
    assert concept["image_file_id"] == uuid.UUID(body["image_file_id"])


def test_image_type_and_size_errors_are_field_level(
    client, tenant, taxonomy, monkeypatch
) -> None:
    category_id, niche_id = taxonomy
    data = {
        "name": "Travel mug",
        "description": "Insulated stainless steel travel mug",
        "category_id": str(category_id),
        "niche_id": str(niche_id),
        "price_minor": "1000",
        "cost_minor": "400",
        "currency": "USD",
    }

    invalid_type = client.post(
        "/product-concepts",
        data=data,
        files={"image": ("mug.txt", PNG_BYTES, "text/plain")},
        headers=_headers(tenant),
    )
    assert invalid_type.status_code == 422
    assert "image" in invalid_type.json()["error"]["fields"]

    monkeypatch.setattr(
        concept_service, "MAX_IMAGE_BYTES", len(PNG_BYTES) - 1
    )
    too_large = client.post(
        "/product-concepts",
        data=data,
        files={"image": ("mug.png", PNG_BYTES, "image/png")},
        headers=_headers(tenant),
    )
    assert too_large.status_code == 422
    assert "image" in too_large.json()["error"]["fields"]


def test_draft_can_be_edited_but_evaluated_row_is_immutable(
    client, tenant, taxonomy, db_engine
) -> None:
    created = _create(client, tenant, taxonomy)
    assert created.status_code == 201
    concept_id = created.json()["id"]

    edited = client.patch(
        f"/product-concepts/{concept_id}",
        json={"price_minor": 1200, "cost_minor": 300},
        headers=_headers(tenant),
    )
    assert edited.status_code == 200
    assert edited.json()["version"] == 2
    assert edited.json()["gross_margin_bp"] == 7500

    reloaded = client.get(
        f"/product-concepts/{concept_id}", headers=_headers(tenant)
    )
    assert reloaded.status_code == 200
    assert reloaded.json()["version"] == 2

    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE product_concepts SET status = 'evaluated' WHERE id = :id"
            ),
            {"id": uuid.UUID(concept_id)},
        )

    blocked = client.patch(
        f"/product-concepts/{concept_id}",
        json={"name": "Changed"},
        headers=_headers(tenant),
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "conflict"

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT name, status, version, price_minor, cost_minor,
                       gross_margin_bp
                FROM product_concepts WHERE id = :id
                """
            ),
            {"id": uuid.UUID(concept_id)},
        ).mappings().one()
    assert row["name"] == "Travel mug"
    assert row["status"] == "evaluated"
    assert row["version"] == 2
    assert row["price_minor"] == 1200
    assert row["cost_minor"] == 300
    assert row["gross_margin_bp"] == 7500


def test_concept_is_scoped_to_the_caller_store(
    client, tenant, make_tenant, taxonomy
) -> None:
    created = _create(client, tenant, taxonomy)
    assert created.status_code == 201
    concept_id = created.json()["id"]

    other = make_tenant()
    response = client.get(
        f"/product-concepts/{concept_id}", headers=_headers(other)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
