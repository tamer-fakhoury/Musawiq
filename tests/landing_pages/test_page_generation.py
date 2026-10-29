"""FR-3.1.2: generate a responsive landing page from the draft."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from musawiq.db.tenant import set_local_tenant
from musawiq.jobs.worker import claim_next, run_job


def _headers(tenant) -> dict[str, str]:
    return {
        "X-Store-Id": str(tenant.store_id),
        "X-User-Id": str(tenant.user_id),
        "X-User-Role": "owner",
    }


def _payload(tenant, **overrides):
    payload = {
        "product_concept_id": str(tenant.concept_id),
        "name": "Coffee Maker",
        "description": "Compact espresso machine",
        "price_minor": 4999,
        "currency": "USD",
        "language": "ar",
        "target_market": "SA",
        "image_file_ids": [],
        "order_method": {"type": "whatsapp", "whatsapp_number": "+966500000000"},
    }
    payload.update(overrides)
    return payload


def _create(client, tenant):
    created = client.post(
        "/landing-pages/drafts", json=_payload(tenant), headers=_headers(tenant)
    )
    assert created.status_code == 201
    return created.json()["id"]


def _run_next_job(db_engine, tenant):
    session = OrmSession(db_engine)
    session.begin()
    set_local_tenant(session, tenant.store_id, tenant.user_id, "owner")
    job = claim_next(session)
    assert job is not None
    finished = run_job(session, job)
    session.commit()
    session.close()
    return finished


def test_generation_renders_responsive_template_as_ai_version(
    client, tenant, db_engine
):
    page_id = _create(client, tenant)

    accepted = client.post(
        f"/landing-pages/{page_id}/generate", headers=_headers(tenant)
    )
    assert accepted.status_code == 202
    job_id = accepted.json()["job_id"]

    finished = _run_next_job(db_engine, tenant)
    assert finished["state"] == "succeeded"

    page = client.get(f"/landing-pages/{page_id}", headers=_headers(tenant))
    body = page.json()
    assert body["draft_version"] == 2
    assert body["generated_by"] == "ai"
    assert body["model_version"] == "template-responsive-v1"

    content = body["content"]
    assert content["template"]["key"] == "responsive"
    assert [section["type"] for section in content["sections"]] == [
        "image",
        "text",
        "text",
        "price",
        "cta",
    ]
    assert content["breakpoints"]["mobile"]["columns"] == 1
    assert content["breakpoints"]["desktop"]["columns"] == 2
    assert content["product"]["name"] == "Coffee Maker"
    assert content["product"]["price_minor"] == 4999

    job = client.get(f"/jobs/{job_id}", headers=_headers(tenant))
    assert job.json()["state"] == "succeeded"


def test_generation_failure_is_reported_and_retryable(
    client, tenant, db_engine
):
    page_id = _create(client, tenant)
    accepted = client.post(
        f"/landing-pages/{page_id}/generate", headers=_headers(tenant)
    )
    job_id = accepted.json()["job_id"]

    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE landing_pages SET status = 'published' WHERE id = :id"),
            {"id": page_id},
        )

    finished = _run_next_job(db_engine, tenant)
    assert finished["state"] == "failed"

    status = client.get(f"/jobs/{job_id}", headers=_headers(tenant)).json()
    assert status["state"] == "failed"
    assert status["error"]["code"] == "not_draft"
    assert status["error"]["message"]

    retried = client.post(f"/jobs/{job_id}/retry", headers=_headers(tenant))
    assert retried.status_code == 202
    assert retried.json()["state"] == "queued"
