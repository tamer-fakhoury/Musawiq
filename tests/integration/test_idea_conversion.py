"""FR-2.2.4 convert a product idea into a draft product concept."""

from __future__ import annotations

import uuid

from sqlalchemy import text


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _seed_idea(engine, tenant, taxonomy) -> dict:
    category_id, niche_id = taxonomy
    run_id = uuid.uuid4()
    idea_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO generation_runs (
                    id, store_id, requested_by, model_version, input_snapshot,
                    requested_count, returned_count, status
                ) VALUES (
                    :id, :store_id, :requested_by, 'rules_v1', '{}'::jsonb,
                    1, 1, 'succeeded'
                )
                """
            ),
            {
                "id": run_id,
                "store_id": tenant.store_id,
                "requested_by": tenant.user_id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO product_ideas (
                    id, store_id, generation_run_id, name, description,
                    category_id, niche_id, rationale, state, model_version
                ) VALUES (
                    :id, :store_id, :run_id, 'Coffee subscription',
                    'Monthly coffee bean subscription', :category_id,
                    :niche_id, 'Uses audience interest in coffee.', 'new',
                    'rules_v1'
                )
                """
            ),
            {
                "id": idea_id,
                "store_id": tenant.store_id,
                "run_id": run_id,
                "category_id": category_id,
                "niche_id": niche_id,
            },
        )
    return {"id": str(idea_id), "run_id": str(run_id)}


def _convert(client, tenant, idea_id: str, **overrides):
    payload = {
        "confirm": True,
        "price_minor": 1000,
        "cost_minor": 400,
        "currency": "USD",
    }
    payload.update(overrides)
    return client.post(
        f"/recommendations/ideas/{idea_id}/convert",
        json=payload,
        headers=_headers(tenant),
    )


def test_conversion_links_both_directions_and_enters_evaluation(
    client, tenant, taxonomy, db_engine
) -> None:
    idea = _seed_idea(db_engine, tenant, taxonomy)
    category_id, niche_id = taxonomy

    response = _convert(client, tenant, idea["id"])
    assert response.status_code == 201, response.text
    concept = response.json()
    assert concept["source_idea_id"] == idea["id"]
    assert concept["status"] == "draft"
    assert concept["name"] == "Coffee subscription"
    assert concept["description"] == "Monthly coffee bean subscription"
    assert concept["category_id"] == str(category_id)
    assert concept["niche_id"] == str(niche_id)
    assert concept["price_minor"] == 1000
    assert concept["cost_minor"] == 400

    with db_engine.connect() as conn:
        linked = conn.execute(
            text(
                """
                SELECT state, converted_concept_id FROM product_ideas
                WHERE id = :id
                """
            ),
            {"id": uuid.UUID(idea["id"])},
        ).mappings().one()
    assert linked["state"] == "converted"
    assert linked["converted_concept_id"] == uuid.UUID(concept["id"])

    repeated = _convert(client, tenant, idea["id"])
    assert repeated.status_code == 201
    assert repeated.json()["id"] == concept["id"]
    with db_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM product_concepts "
                "WHERE source_idea_id = :idea_id"
            ),
            {"idea_id": uuid.UUID(idea["id"])},
        ).scalar_one()
    assert count == 1

    edited = client.patch(
        f"/product-concepts/{concept['id']}",
        json={"name": "Coffee club"},
        headers=_headers(tenant),
    )
    assert edited.status_code == 200

    evaluation = client.post(
        f"/product-concepts/{concept['id']}/evaluations",
        headers=_headers(tenant),
    )
    assert evaluation.status_code == 201, evaluation.text


def test_conversion_requires_confirmation_and_merchant_price_fields(
    client, tenant, taxonomy, db_engine
) -> None:
    idea = _seed_idea(db_engine, tenant, taxonomy)

    unconfirmed = _convert(client, tenant, idea["id"], confirm=False)
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["error"]["code"] == "confirmation_required"

    missing = _convert(
        client,
        tenant,
        idea["id"],
        price_minor=None,
        cost_minor=None,
        currency=None,
    )
    assert missing.status_code == 422
    fields = missing.json()["error"]["fields"]
    assert {"price_minor", "cost_minor", "currency"} <= set(fields)

    with db_engine.connect() as conn:
        state = conn.execute(
            text("SELECT state FROM product_ideas WHERE id = :id"),
            {"id": uuid.UUID(idea["id"])},
        ).scalar_one()
    assert state == "new"


def test_conversion_allows_editable_overrides_and_is_store_scoped(
    client, tenant, make_tenant, taxonomy, db_engine
) -> None:
    idea = _seed_idea(db_engine, tenant, taxonomy)
    response = _convert(
        client,
        tenant,
        idea["id"],
        name="Edited idea name",
        description="Edited idea description",
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Edited idea name"
    assert response.json()["description"] == "Edited idea description"

    other = make_tenant()
    hidden = _convert(client, other, idea["id"])
    assert hidden.status_code == 404
