"""FR-2.2.1 recommendation generation and idea library."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb
from sqlalchemy import text

from musawiq.services import recommendations as recommendation_service
from musawiq.services.recommendations import _is_duplicate, _normalized
from musawiq.workers.recommendation_generation import (
    run_recommendation_generation_job,
)


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _seed_inputs(engine, tenant, taxonomy) -> None:
    category_id, niche_id = taxonomy
    profile_id = uuid.uuid4()
    order_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
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
                    age_min, age_max, interests, languages
                ) VALUES (
                    :store_id, :profile_id, 'Core', :locations, 18, 40,
                    CAST(:interests AS text[]), CAST(:languages AS text[])
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "profile_id": profile_id,
                "locations": Jsonb(["SA"]),
                "interests": ["coffee"],
                "languages": ["en"],
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO orders (
                    id, store_id, origin, status, currency, placed_at
                ) VALUES (
                    :id, :store_id, 'imported', 'fulfilled', 'USD', :placed_at
                )
                """
            ),
            {
                "id": order_id,
                "store_id": tenant.store_id,
                "placed_at": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO order_items (
                    store_id, order_id, product_name_snapshot, quantity,
                    unit_price_minor, line_total_minor, currency
                ) VALUES (
                    :store_id, :order_id, 'Classic Mug', 5, 1000, 5000, 'USD'
                )
                """
            ),
            {"store_id": tenant.store_id, "order_id": order_id},
        )
    assert category_id is not None


def _generate(client, tenant, count: int = 3) -> dict:
    response = client.post(
        "/recommendations/generate",
        json={"count": count},
        headers=_headers(tenant),
    )
    assert response.status_code == 202, response.text
    return response.json()


def _run_job(engine, job_id: str):
    with engine.connect() as conn:
        job = conn.execute(
            text("SELECT * FROM async_jobs WHERE id = :id"),
            {"id": uuid.UUID(job_id)},
        ).mappings().one()
    return run_recommendation_generation_job(dict(job))


def _ideas(client, tenant, run_id: str) -> list[dict]:
    response = client.get(
        "/recommendations/ideas",
        params={"generation_run_id": run_id},
        headers=_headers(tenant),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_generation_is_async_stores_metadata_and_returns_configurable_ideas(
    client, tenant, taxonomy, db_engine
) -> None:
    _seed_inputs(db_engine, tenant, taxonomy)
    created = _generate(client, tenant, count=3)
    assert created["status"] == "queued"

    outcome = _run_job(db_engine, created["job_id"])
    assert outcome.state == "succeeded"
    assert outcome.result["returned_count"] == 3

    run_response = client.get(
        f"/recommendations/runs/{created['run_id']}",
        headers=_headers(tenant),
    )
    assert run_response.status_code == 200
    run = run_response.json()
    assert run["status"] == "succeeded"
    assert run["requested_count"] == 3
    assert run["returned_count"] == 3
    assert run["model_version"] == "rules_v1"
    assert run["started_at"] is not None
    assert run["finished_at"] is not None
    assert run["input_snapshot"]["schema_version"] == 1
    assert run["input_snapshot"]["niches"]
    assert run["input_snapshot"]["segments"]
    assert run["input_snapshot"]["sales_history"]
    assert run["input_snapshot"]["competitive_data"]["status"] == "missing"

    ideas = _ideas(client, tenant, created["run_id"])
    assert len(ideas) == 3
    assert all(idea["state"] == "new" for idea in ideas)
    assert all(idea["generation_run_id"] == created["run_id"] for idea in ideas)
    assert all(idea["model_version"] == "rules_v1" for idea in ideas)
    assert all(idea["rationale"] for idea in ideas)
    assert all(len(idea["evidence"]) == 1 for idea in ideas)
    assert all(
        evidence["evidence_type"] == "hypothesis"
        and evidence["source_url"] is None
        for idea in ideas
        for evidence in idea["evidence"]
    )


def test_idea_evidence_labels_staleness_and_stored_links(
    client, tenant, taxonomy, db_engine
) -> None:
    _seed_inputs(db_engine, tenant, taxonomy)
    created = _generate(client, tenant, count=1)
    _run_job(db_engine, created["job_id"])
    idea = _ideas(client, tenant, created["run_id"])[0]

    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO idea_evidences (
                    store_id, product_idea_id, evidence_type, claim,
                    source_name, source_url, source_published_at,
                    retrieved_at, confidence
                ) VALUES (
                    :store_id, :idea_id, 'verified', 'Market source claim',
                    'Market report', 'https://example.com/report',
                    :published_at, :retrieved_at, 0.9
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "idea_id": uuid.UUID(idea["id"]),
                "published_at": datetime.now(timezone.utc) - timedelta(days=500),
                "retrieved_at": datetime.now(timezone.utc),
            },
        )

    response = client.get(
        f"/recommendations/ideas/{idea['id']}",
        headers=_headers(tenant),
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["evidence"]
    verified = next(
        item for item in evidence if item["evidence_type"] == "verified"
    )
    hypothesis = next(
        item for item in evidence if item["evidence_type"] == "hypothesis"
    )
    assert verified["label"] == "Verified"
    assert verified["source_url"] == "https://example.com/report"
    assert verified["is_stale"] is True
    assert hypothesis["label"] == "AI Hypothesis"
    assert hypothesis["source_url"] is None
    assert hypothesis["is_stale"] is False


def test_save_dismiss_and_restore_are_audited_and_store_scoped(
    client, tenant, make_tenant, taxonomy, db_engine
) -> None:
    _seed_inputs(db_engine, tenant, taxonomy)
    created = _generate(client, tenant, count=1)
    _run_job(db_engine, created["job_id"])
    idea = _ideas(client, tenant, created["run_id"])[0]

    saved = client.post(
        f"/recommendations/ideas/{idea['id']}/save",
        headers=_headers(tenant),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["state"] == "saved"

    dismissed = client.post(
        f"/recommendations/ideas/{idea['id']}/dismiss",
        json={"reason": "Not aligned with current inventory"},
        headers=_headers(tenant),
    )
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json()["state"] == "dismissed"
    assert (
        dismissed.json()["dismissed_reason"]
        == "Not aligned with current inventory"
    )

    listed = client.get(
        "/recommendations/ideas",
        params={"state": "dismissed"},
        headers=_headers(tenant),
    )
    assert [item["id"] for item in listed.json()] == [idea["id"]]

    with db_engine.connect() as conn:
        audits = conn.execute(
            text(
                """
                SELECT action, actor_user_id, before, after
                FROM audit_logs
                WHERE store_id = :store_id AND target_id = :idea_id
                ORDER BY created_at, id
                """
            ),
            {"store_id": tenant.store_id, "idea_id": uuid.UUID(idea["id"])},
        ).mappings().all()
    assert [row["action"] for row in audits] == [
        "product_idea.saved",
        "product_idea.dismissed",
    ]
    assert {row["actor_user_id"] for row in audits} == {tenant.user_id}
    assert audits[0]["before"]["state"] == "new"
    assert audits[0]["after"]["state"] == "saved"
    assert audits[1]["before"]["state"] == "saved"
    assert audits[1]["after"]["state"] == "dismissed"

    restored = client.post(
        f"/recommendations/ideas/{idea['id']}/restore",
        headers=_headers(tenant),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["state"] == "new"
    assert restored.json()["dismissed_reason"] is None

    other = make_tenant()
    hidden = client.post(
        f"/recommendations/ideas/{idea['id']}/dismiss",
        headers=_headers(other),
    )
    assert hidden.status_code == 404


def test_generation_deduplicates_existing_concepts_and_dismissed_ideas(
    client, tenant, taxonomy, db_engine
) -> None:
    _seed_inputs(db_engine, tenant, taxonomy)
    first = _generate(client, tenant, count=1)
    _run_job(db_engine, first["job_id"])
    first_idea = _ideas(client, tenant, first["run_id"])[0]

    category_id, niche_id = taxonomy
    concept = client.post(
        "/product-concepts",
        json={
            "name": first_idea["name"],
            "description": first_idea["description"],
            "category_id": str(category_id),
            "niche_id": str(niche_id),
            "price_minor": 1000,
            "cost_minor": 400,
            "currency": "USD",
        },
        headers=_headers(tenant),
    )
    assert concept.status_code == 201, concept.text

    second = _generate(client, tenant, count=3)
    _run_job(db_engine, second["job_id"])
    second_ideas = _ideas(client, tenant, second["run_id"])
    assert first_idea["name"] not in {idea["name"] for idea in second_ideas}

    dismissed_source = second_ideas[0]
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO product_ideas (
                    store_id, generation_run_id, name, description,
                    rationale, state, model_version
                ) VALUES (
                    :store_id, :run_id, :name, :description, 'Dismissed',
                    'dismissed', 'rules_v1'
                )
                """
            ),
            {
                "store_id": tenant.store_id,
                "run_id": uuid.UUID(second["run_id"]),
                "name": dismissed_source["name"],
                "description": dismissed_source["description"],
            },
        )

    third = _generate(client, tenant, count=3)
    _run_job(db_engine, third["job_id"])
    third_ideas = _ideas(client, tenant, third["run_id"])
    assert dismissed_source["name"] not in {
        idea["name"] for idea in third_ideas
    }


def test_generation_fails_cleanly_without_niche_or_sales_history(
    client, tenant, db_engine
) -> None:
    created = _generate(client, tenant, count=2)
    outcome = _run_job(db_engine, created["job_id"])
    assert outcome.state == "failed"
    assert "No niche or sales history" in outcome.error_message

    run = client.get(
        f"/recommendations/runs/{created['run_id']}",
        headers=_headers(tenant),
    ).json()
    assert run["status"] == "failed"
    assert "No niche or sales history" in run["error_message"]
    assert _ideas(client, tenant, created["run_id"]) == []


def test_idea_library_filters_and_store_scope(
    client, tenant, make_tenant, taxonomy, db_engine
) -> None:
    _seed_inputs(db_engine, tenant, taxonomy)
    created = _generate(client, tenant, count=2)
    _run_job(db_engine, created["job_id"])

    new_ideas = client.get(
        "/recommendations/ideas",
        params={"state": "new"},
        headers=_headers(tenant),
    )
    assert new_ideas.status_code == 200
    assert len(new_ideas.json()) == 2

    other = make_tenant()
    other_ideas = client.get(
        "/recommendations/ideas", headers=_headers(other)
    )
    assert other_ideas.status_code == 200
    assert other_ideas.json() == []

    other_run = client.get(
        f"/recommendations/runs/{created['run_id']}",
        headers=_headers(other),
    )
    assert other_run.status_code == 404

def test_arabic_dedupe_normalization_preserves_letters() -> None:
    normalized = _normalized("قَهْوَة عربية")
    assert normalized
    assert normalized == _normalized("قهوة عربية")
    assert _is_duplicate(
        "قهوة عربية",
        "مشروب ساخن",
        [_normalized("قهوة عربية مشروب ساخن")],
    )


def test_failed_generation_rolls_back_partial_ideas(
    client, tenant, taxonomy, db_engine, monkeypatch
) -> None:
    _seed_inputs(db_engine, tenant, taxonomy)
    created = _generate(client, tenant, count=3)
    original = recommendation_service.IdeaEvidenceRepository.insert_evidence
    calls = {"count": 0}

    def flaky(self, values):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("internal database detail")
        return original(self, values)

    monkeypatch.setattr(
        recommendation_service.IdeaEvidenceRepository,
        "insert_evidence",
        flaky,
    )
    outcome = _run_job(db_engine, created["job_id"])
    assert outcome.state == "failed"

    run = client.get(
        f"/recommendations/runs/{created['run_id']}",
        headers=_headers(tenant),
    ).json()
    assert run["status"] == "failed"
    assert "internal database detail" not in run["error_message"]
    assert _ideas(client, tenant, created["run_id"]) == []


def test_retried_generation_is_idempotent(
    client, tenant, taxonomy, db_engine
) -> None:
    _seed_inputs(db_engine, tenant, taxonomy)
    created = _generate(client, tenant, count=2)
    first = _run_job(db_engine, created["job_id"])
    assert first.state == "succeeded"
    ideas = _ideas(client, tenant, created["run_id"])
    assert len(ideas) == 2

    second = _run_job(db_engine, created["job_id"])
    assert second.state == "succeeded"
    assert _ideas(client, tenant, created["run_id"]) == ideas

def test_generate_endpoint_honors_idempotency_key(
    client, tenant, taxonomy, db_engine
) -> None:
    _seed_inputs(db_engine, tenant, taxonomy)
    headers = {**_headers(tenant), "Idempotency-Key": "recommendation-once"}
    first = client.post(
        "/recommendations/generate", json={"count": 2}, headers=headers
    )
    second = client.post(
        "/recommendations/generate", json={"count": 2}, headers=headers
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]
    assert first.json()["job_id"] == second.json()["job_id"]

    with db_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM async_jobs "
                "WHERE idempotency_key = 'recommendation-once'"
            )
        ).scalar_one()
    assert count == 1
