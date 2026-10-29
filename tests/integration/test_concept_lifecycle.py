"""FR-2.1.2 product concept lifecycle, listing, and deletion guard."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text


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
        "currency": "USD",
    }
    payload.update(overrides)
    return payload


def _create(client, tenant, taxonomy, **overrides):
    response = client.post(
        "/product-concepts",
        json=_payload(taxonomy, **overrides),
        headers=_headers(tenant),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_evaluation(
    engine,
    tenant,
    concept_id: str,
    score: float,
    *,
    evaluated_at: datetime | None = None,
) -> None:
    suffix = uuid.uuid4().hex
    with engine.begin() as conn:
        model_id = conn.execute(
            text(
                """
                INSERT INTO scoring_models (
                    store_id, key, version, name, weights, effective_from
                ) VALUES (
                    :store_id, :key, 1, 'Lifecycle Model', '{}'::jsonb, now()
                )
                RETURNING id
                """
            ),
            {"store_id": tenant.store_id, "key": f"lifecycle-{suffix}"},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO evaluations (
                    store_id, product_concept_id, scoring_model_id,
                    model_version, score, confidence, is_reliable,
                    input_snapshot, evaluated_at
                ) VALUES (
                    :store_id, :concept_id, :model_id,
                    1, :score, 'high', true, '{}'::jsonb, :evaluated_at
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "concept_id": uuid.UUID(concept_id),
                "model_id": model_id,
                "score": score,
                "evaluated_at": evaluated_at or datetime.now(timezone.utc),
            },
        )


def _make_category(engine, name: str) -> uuid.UUID:
    category_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO categories (id, name, slug, is_active, sort_order)
                VALUES (:id, :name, :slug, true, 1)
                """
            ),
            {
                "id": category_id,
                "name": name,
                "slug": f"lifecycle-{suffix}",
            },
        )
    return category_id


def test_list_filters_searches_sorts_and_reports_latest_score(
    client, tenant, make_tenant, taxonomy, db_engine
) -> None:
    mug = _create(client, tenant, taxonomy, name="Travel mug")
    lamp = _create(
        client,
        tenant,
        taxonomy,
        name="Desk lamp",
        description="Warm reading light",
    )
    hose = _create(
        client,
        tenant,
        taxonomy,
        name="Garden hose",
        description="Outdoor watering",
    )

    _add_evaluation(
        db_engine,
        tenant,
        mug["id"],
        10,
        evaluated_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    _add_evaluation(db_engine, tenant, mug["id"], 80)
    _add_evaluation(db_engine, tenant, lamp["id"], 92)

    other = make_tenant()
    _create(client, other, taxonomy, name="Other store mug")

    by_score = client.get(
        "/product-concepts",
        params={"sort": "score", "direction": "desc"},
        headers=_headers(tenant),
    )
    assert by_score.status_code == 200
    items = by_score.json()
    assert [item["id"] for item in items] == [
        lamp["id"],
        mug["id"],
        hose["id"],
    ]
    assert items[0]["latest_score"] == 92.0
    assert items[1]["latest_score"] == 80.0
    assert items[2]["latest_score"] is None

    searched = client.get(
        "/product-concepts",
        params={"search": "mug"},
        headers=_headers(tenant),
    )
    assert [item["id"] for item in searched.json()] == [mug["id"]]

    described = client.get(
        "/product-concepts",
        params={"q": "reading light"},
        headers=_headers(tenant),
    )
    assert [item["id"] for item in described.json()] == [lamp["id"]]

    second_category = _make_category(db_engine, "Home")
    home = _create(
        client,
        tenant,
        taxonomy,
        name="Home item",
        category_id=str(second_category),
        niche_id=None,
    )
    filtered = client.get(
        "/product-concepts",
        params={"category_id": str(second_category)},
        headers=_headers(tenant),
    )
    assert [item["id"] for item in filtered.json()] == [home["id"]]

    by_category = client.get(
        "/product-concepts",
        params={"sort": "category", "direction": "asc"},
        headers=_headers(tenant),
    )
    assert [item["id"] for item in by_category.json()] == [
        hose["id"],
        lamp["id"],
        mug["id"],
        home["id"],
    ]

    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE product_concepts SET status = 'evaluated' "
                "WHERE id = :id"
            ),
            {"id": uuid.UUID(mug["id"])},
        )
    by_status = client.get(
        "/product-concepts",
        params={"status": "evaluated"},
        headers=_headers(tenant),
    )
    assert [item["id"] for item in by_status.json()] == [mug["id"]]


def test_list_filters_by_created_date(client, tenant, taxonomy) -> None:
    concept = _create(client, tenant, taxonomy)
    today = datetime.now(timezone.utc).date().isoformat()
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()

    included = client.get(
        "/product-concepts",
        params={"created_from": today, "created_to": today},
        headers=_headers(tenant),
    )
    assert [item["id"] for item in included.json()] == [concept["id"]]

    excluded = client.get(
        "/product-concepts",
        params={"date_from": tomorrow},
        headers=_headers(tenant),
    )
    assert excluded.json() == []


def test_invalid_list_filters_return_field_errors(
    client, tenant
) -> None:
    invalid_status = client.get(
        "/product-concepts",
        params={"status": "deleted"},
        headers=_headers(tenant),
    )
    assert invalid_status.status_code == 422
    assert "status" in invalid_status.json()["error"]["fields"]

    invalid_sort = client.get(
        "/product-concepts",
        params={"sort": "name"},
        headers=_headers(tenant),
    )
    assert invalid_sort.status_code == 422
    assert "sort" in invalid_sort.json()["error"]["fields"]


def test_archive_is_reversible_for_draft_and_evaluated_concepts(
    client, tenant, taxonomy, db_engine
) -> None:
    draft = _create(client, tenant, taxonomy)

    archived = client.post(
        f"/product-concepts/{draft['id']}/archive",
        headers=_headers(tenant),
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["version"] == 2

    restored = client.post(
        f"/product-concepts/{draft['id']}/unarchive",
        headers=_headers(tenant),
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "draft"
    assert restored.json()["version"] == 3

    patched_archive = client.patch(
        f"/product-concepts/{draft['id']}",
        json={"status": "archived", "version": 3},
        headers=_headers(tenant),
    )
    assert patched_archive.status_code == 200
    assert patched_archive.json()["status"] == "archived"
    assert patched_archive.json()["version"] == 4

    patched_restore = client.patch(
        f"/product-concepts/{draft['id']}",
        json={"status": "draft", "version": 4},
        headers=_headers(tenant),
    )
    assert patched_restore.status_code == 200
    assert patched_restore.json()["status"] == "draft"
    assert patched_restore.json()["version"] == 5

    evaluated = _create(client, tenant, taxonomy, name="Evaluated concept")
    _add_evaluation(db_engine, tenant, evaluated["id"], 75)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE product_concepts SET status = 'evaluated' "
                "WHERE id = :id"
            ),
            {"id": uuid.UUID(evaluated["id"])},
        )

    archived_evaluated = client.post(
        f"/product-concepts/{evaluated['id']}/archive",
        headers=_headers(tenant),
    )
    assert archived_evaluated.status_code == 200
    assert archived_evaluated.json()["status"] == "archived"

    restored_evaluated = client.post(
        f"/product-concepts/{evaluated['id']}/unarchive",
        headers=_headers(tenant),
    )
    assert restored_evaluated.status_code == 200
    assert restored_evaluated.json()["status"] == "evaluated"


def test_hard_delete_is_allowed_only_without_an_evaluation(
    client, tenant, taxonomy, db_engine
) -> None:
    removable = _create(client, tenant, taxonomy)
    deleted = client.delete(
        f"/product-concepts/{removable['id']}",
        headers=_headers(tenant),
    )
    assert deleted.status_code == 204

    missing = client.get(
        f"/product-concepts/{removable['id']}",
        headers=_headers(tenant),
    )
    assert missing.status_code == 404

    evaluated = _create(client, tenant, taxonomy, name="Keep me")
    _add_evaluation(db_engine, tenant, evaluated["id"], 60)
    blocked = client.delete(
        f"/product-concepts/{evaluated['id']}",
        headers=_headers(tenant),
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "conflict"

    still_there = client.get(
        f"/product-concepts/{evaluated['id']}",
        headers=_headers(tenant),
    )
    assert still_there.status_code == 200


def test_edits_reject_stale_versions_and_accept_if_match(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create(client, tenant, taxonomy)

    first = client.patch(
        f"/product-concepts/{concept['id']}",
        json={"name": "First edit", "version": 1},
        headers=_headers(tenant),
    )
    assert first.status_code == 200
    assert first.json()["version"] == 2

    stale = client.patch(
        f"/product-concepts/{concept['id']}",
        json={"name": "Stale edit", "version": 1},
        headers=_headers(tenant),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "conflict"

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT name, version FROM product_concepts WHERE id = :id"
            ),
            {"id": uuid.UUID(concept["id"])},
        ).mappings().one()
    assert row["name"] == "First edit"
    assert row["version"] == 2

    header_edit = client.patch(
        f"/product-concepts/{concept['id']}",
        json={"price_minor": 1200},
        headers={**_headers(tenant), "If-Match": '"2"'},
    )
    assert header_edit.status_code == 200
    assert header_edit.json()["version"] == 3

    stale_header = client.patch(
        f"/product-concepts/{concept['id']}",
        json={"price_minor": 1300},
        headers={**_headers(tenant), "If-Match": '"2"'},
    )
    assert stale_header.status_code == 409

    mismatched = client.patch(
        f"/product-concepts/{concept['id']}",
        json={"price_minor": 1400, "version": 3},
        headers={**_headers(tenant), "If-Match": '"4"'},
    )
    assert mismatched.status_code == 422
    assert "version" in mismatched.json()["error"]["fields"]


def test_lifecycle_is_scoped_to_the_caller_store(
    client, tenant, make_tenant, taxonomy
) -> None:
    concept = _create(client, tenant, taxonomy)
    other = make_tenant()

    listed = client.get("/product-concepts", headers=_headers(other))
    assert listed.json() == []

    archived = client.post(
        f"/product-concepts/{concept['id']}/archive",
        headers=_headers(other),
    )
    assert archived.status_code == 404

    deleted = client.delete(
        f"/product-concepts/{concept['id']}",
        headers=_headers(other),
    )
    assert deleted.status_code == 404
