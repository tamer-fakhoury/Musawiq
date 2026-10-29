"""FR-2.1.4/FR-2.1.5 viability evaluation and explanation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb
from sqlalchemy import text

from musawiq.services.scoring.explain import (
    GUARANTEE_PHRASES,
    contains_guarantee_language,
)
from musawiq.workers.batch_evaluation import run_batch_evaluation_job


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


def _seed_orders(engine, tenant, *, count: int = 20) -> None:
    now = datetime.now(timezone.utc)
    step = 30 / (count - 1)
    with engine.begin() as conn:
        for index in range(count):
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
                    "placed_at": now - timedelta(days=30 - index * step),
                },
            )


def _seed_audience(engine, tenant, niche_id) -> None:
    profile_id = uuid.uuid4()
    with engine.begin() as conn:
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


def _available_inputs(engine, tenant, taxonomy) -> None:
    _seed_orders(engine, tenant)
    _seed_audience(engine, tenant, taxonomy[1])


def _evaluate(client, tenant, concept_id: str):
    return client.post(
        f"/product-concepts/{concept_id}/evaluations",
        headers=_headers(tenant),
    )


def test_evaluation_is_deterministic_and_records_model_and_inputs(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(
        client, tenant, taxonomy, name="Low margin", price=1000, cost=900
    )
    _available_inputs(db_engine, tenant, taxonomy)

    first = _evaluate(client, tenant, concept["id"])
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["score"] is not None
    assert body["score"] > 0
    assert body["score_scale"] == 100
    assert body["confidence"] == "medium"
    assert body["is_reliable"] is True
    assert body["model_version"] == 1
    assert body["input_snapshot"]["schema_version"] == 1
    assert body["input_snapshot"]["model"]["version"] == 1
    assert body["input_snapshot"]["model"]["weights"]
    assert len(body["factors"]) == 4

    second = _evaluate(client, tenant, concept["id"])
    assert second.status_code == 201
    assert second.json()["id"] == body["id"]
    assert second.json()["score"] == body["score"]

    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT score, score_scale, confidence, is_reliable,
                       sufficiency_check_id, input_snapshot, evaluated_at
                FROM evaluations WHERE id = :id
                """
            ),
            {"id": uuid.UUID(body["id"])},
        ).mappings().one()
        factor_count = conn.execute(
            text(
                "SELECT count(*) FROM score_factors "
                "WHERE evaluation_id = :id"
            ),
            {"id": uuid.UUID(body["id"])},
        ).scalar_one()
    assert float(row["score"]) == body["score"]
    assert row["score_scale"] == 100
    assert row["confidence"] == "medium"
    assert row["is_reliable"] is True
    assert row["sufficiency_check_id"] is not None
    assert row["input_snapshot"]["model"]["weights"]
    assert row["evaluated_at"] is not None
    assert factor_count == 4


def test_explanation_returns_ranked_factors_limitations_and_provenance(
    client, tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(
        client, tenant, taxonomy, name="Thin margin", price=1000, cost=950
    )
    _available_inputs(db_engine, tenant, taxonomy)
    evaluation = _evaluate(client, tenant, concept["id"]).json()

    response = client.get(
        f"/evaluations/{evaluation['id']}/explanation",
        headers=_headers(tenant),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["score"] == evaluation["score"]
    assert body["confidence"] == "medium"
    assert body["top_positive"]
    assert body["top_negative"]
    assert body["top_negative"][0]["factor_key"] == "margin"
    assert "Competitive data is missing." in body["limitations"]
    assert "competitive_data" in body["inferred_inputs"]
    assert "margin" in body["measured_inputs"]
    assert "sales_history" in body["measured_inputs"]
    assert body["sufficiency_check"]["overall_status"] == "sufficient"

    rendered = str(body).lower()
    for phrase in GUARANTEE_PHRASES:
        assert phrase not in rendered
    assert contains_guarantee_language(body["summary"]) is False


def test_missing_critical_inputs_yield_null_score_and_limitations(
    client, tenant, taxonomy
) -> None:
    concept = _create_concept(client, tenant, taxonomy, name="No data")

    evaluation = _evaluate(client, tenant, concept["id"])
    assert evaluation.status_code == 201, evaluation.text
    body = evaluation.json()
    assert body["score"] is None
    assert body["confidence"] == "low"
    assert body["is_reliable"] is False

    explanation = client.get(
        f"/evaluations/{body['id']}/explanation",
        headers=_headers(tenant),
    )
    assert explanation.status_code == 200
    payload = explanation.json()
    assert payload["score"] is None
    assert "Sales history is missing." in payload["limitations"]
    assert "Audience data is missing." in payload["limitations"]
    assert "unavailable" in payload["summary"].lower()


def test_batch_evaluation_job_reports_per_concept_results(
    client, tenant, taxonomy, db_engine
) -> None:
    first = _create_concept(client, tenant, taxonomy, name="First")
    second = _create_concept(client, tenant, taxonomy, name="Second")
    _available_inputs(db_engine, tenant, taxonomy)

    response = client.post(
        "/evaluations/batch",
        json={"concept_ids": [first["id"], second["id"]]},
        headers=_headers(tenant),
    )
    assert response.status_code == 202, response.text
    job_id = uuid.UUID(response.json()["id"])

    with db_engine.connect() as conn:
        job = conn.execute(
            text("SELECT * FROM async_jobs WHERE id = :id"),
            {"id": job_id},
        ).mappings().one()

    outcome = run_batch_evaluation_job(dict(job))
    assert outcome.state == "succeeded"
    assert outcome.result["succeeded"] == 2
    assert outcome.result["failed"] == 0
    assert len(outcome.result["results"]) == 2

    with db_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM evaluations WHERE store_id = :store_id"
            ),
            {"store_id": tenant.store_id},
        ).scalar_one()
    assert count == 2


def test_other_store_cannot_read_evaluation(
    client, tenant, make_tenant, taxonomy, db_engine
) -> None:
    concept = _create_concept(client, tenant, taxonomy, name="Private")
    _available_inputs(db_engine, tenant, taxonomy)
    evaluation = _evaluate(client, tenant, concept["id"]).json()
    other = make_tenant()

    response = client.get(
        f"/evaluations/{evaluation['id']}/explanation",
        headers=_headers(other),
    )
    assert response.status_code == 404
