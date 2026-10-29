"""FR-2.1.6 concept comparison, selection, and handoff."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb
from sqlalchemy import text


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _create_concept(
    client, tenant, taxonomy, *, name: str, price: int = 1000, cost: int = 400
) -> dict:
    category_id, niche_id = taxonomy
    response = client.post(
        "/product-concepts",
        json={
            "name": name,
            "description": f"{name} description",
            "category_id": str(category_id),
            "niche_id": str(niche_id),
            "price_minor": price,
            "cost_minor": cost,
            "currency": "USD",
        },
        headers=_headers(tenant),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_available_inputs(engine, tenant, niche_id) -> None:
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        for index in range(20):
            conn.execute(
                text(
                    """
                    INSERT INTO orders (
                        store_id, origin, status, currency, placed_at
                    ) VALUES (
                        :store_id, 'imported', 'fulfilled', 'USD', :placed_at
                    )
                    """
                ),
                {
                    "store_id": tenant.store_id,
                    "placed_at": now - timedelta(
                        days=30 - index * (30 / 19)
                    ),
                },
            )
        profile_id = uuid.uuid4()
        conn.execute(
            text(
                """
                INSERT INTO audience_profiles (
                    id, store_id, version, status, is_current,
                    niche_ids, languages, created_by
                ) VALUES (
                    :id, :store_id, 1, 'active', true,
                    CAST(:niche_ids AS uuid[]), CAST(:languages AS text[]),
                    :created_by
                )
                """
            ),
            {
                "id": profile_id,
                "store_id": tenant.store_id,
                "niche_ids": [niche_id],
                "languages": ["en"],
                "created_by": tenant.user_id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO audience_segments (
                    store_id, audience_profile_id, label, locations,
                    age_min, age_max
                ) VALUES (
                    :store_id, :profile_id, 'Core', :locations, 18, 40
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "profile_id": profile_id,
                "locations": Jsonb(["SA"]),
            },
        )


def _evaluate(client, tenant, concept_id: str) -> dict:
    response = client.post(
        f"/product-concepts/{concept_id}/evaluations",
        headers=_headers(tenant),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _evaluated_pair(client, tenant, taxonomy, engine) -> tuple[dict, dict]:
    first = _create_concept(client, tenant, taxonomy, name="High margin")
    second = _create_concept(
        client, tenant, taxonomy, name="Low margin", price=1000, cost=900
    )
    _seed_available_inputs(engine, tenant, taxonomy[1])
    _evaluate(client, tenant, first["id"])
    _evaluate(client, tenant, second["id"])
    return first, second


def test_compare_returns_side_by_side_metrics_and_top_factors(
    client, tenant, taxonomy, db_engine
) -> None:
    first, second = _evaluated_pair(
        client, tenant, taxonomy, db_engine
    )

    response = client.post(
        "/product-concepts/compare",
        json={"concept_ids": [first["id"], second["id"]]},
        headers=_headers(tenant),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 2
    assert [item["concept_id"] for item in body["concepts"]] == [
        first["id"],
        second["id"],
    ]
    high, low = body["concepts"]
    assert high["score"] > low["score"]
    assert high["confidence"] == "medium"
    assert high["category"] == "Concepts Test"
    assert high["price_minor"] == 1000
    assert high["gross_margin_bp"] == 6000
    assert high["top_factors"]
    assert {
        factor["factor_key"] for factor in high["top_factors"]
    } >= {"margin", "sales_history"}


def test_selection_transitions_state_and_writes_audit(
    client, tenant, taxonomy, db_engine
) -> None:
    first, second = _evaluated_pair(
        client, tenant, taxonomy, db_engine
    )

    response = client.post(
        "/product-concepts/select",
        json={"concept_ids": [first["id"], second["id"]]},
        headers=_headers(tenant),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["selected_ids"] == [first["id"], second["id"]]
    assert {item["status"] for item in body["concepts"]} == {"selected"}

    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT status, version FROM product_concepts
                WHERE store_id = :store_id
                ORDER BY name
                """
            ),
            {"store_id": tenant.store_id},
        ).mappings().all()
    assert {row["status"] for row in rows} == {"selected"}
    assert {row["version"] for row in rows} == {3}

    audits = None
    with db_engine.connect() as conn:
        audits = conn.execute(
            text(
                """
                SELECT actor_user_id, target_id, action, before, after,
                       created_at
                FROM audit_logs
                WHERE store_id = :store_id
                ORDER BY created_at, id
                """
            ),
            {"store_id": tenant.store_id},
        ).mappings().all()
    assert len(audits) == 2
    assert {row["actor_user_id"] for row in audits} == {tenant.user_id}
    assert {row["action"] for row in audits} == {
        "product_concept.selected"
    }
    assert all(row["created_at"] is not None for row in audits)
    assert all(row["before"]["status"] == "evaluated" for row in audits)
    assert all(row["after"]["status"] == "selected" for row in audits)

    repeated = client.post(
        "/product-concepts/select",
        json={"concept_ids": [first["id"], second["id"]]},
        headers=_headers(tenant),
    )
    assert repeated.status_code == 200
    with db_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE store_id = :store_id"
            ),
            {"store_id": tenant.store_id},
        ).scalar_one()
    assert count == 2


def test_unevaluated_and_archived_concepts_cannot_be_selected(
    client, tenant, taxonomy, db_engine
) -> None:
    draft = _create_concept(client, tenant, taxonomy, name="Draft")

    rejected = client.post(
        "/product-concepts/select",
        json={"concept_ids": [draft["id"]]},
        headers=_headers(tenant),
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "conflict"

    evaluated = _create_concept(
        client, tenant, taxonomy, name="Archived evaluated"
    )
    _seed_available_inputs(db_engine, tenant, taxonomy[1])
    _evaluate(client, tenant, evaluated["id"])
    archived = client.post(
        f"/product-concepts/{evaluated['id']}/archive",
        headers=_headers(tenant),
    )
    assert archived.status_code == 200

    archived_selection = client.post(
        "/product-concepts/select",
        json={"concept_ids": [evaluated["id"]]},
        headers=_headers(tenant),
    )
    assert archived_selection.status_code == 409


def test_compare_rejects_unevaluated_and_cross_store_concepts(
    client, tenant, make_tenant, taxonomy
) -> None:
    draft = _create_concept(client, tenant, taxonomy, name="Draft")
    local = client.post(
        "/product-concepts/compare",
        json={"concept_ids": [draft["id"]]},
        headers=_headers(tenant),
    )
    assert local.status_code == 409

    other = make_tenant()
    cross_store = client.post(
        "/product-concepts/compare",
        json={"concept_ids": [draft["id"]]},
        headers=_headers(other),
    )
    assert cross_store.status_code == 404
