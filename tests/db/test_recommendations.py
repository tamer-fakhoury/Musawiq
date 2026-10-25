"""Recommendation tables: constraints and circular FK (DB-0.8)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def _insert_user(conn, email="owner@example.com"):
    return conn.execute(
        text(
            """
            INSERT INTO users (email, full_name, role, status)
            VALUES (:email, 'Test User', 'owner', 'active')
            RETURNING id
            """
        ),
        {"email": email},
    ).scalar_one()


def _insert_store(conn, owner_user_id, slug="demo-store"):
    return conn.execute(
        text(
            """
            INSERT INTO stores (
                owner_user_id, name, slug, status,
                default_currency, default_language, timezone, country_code,
                onboarding_status
            )
            VALUES (
                :owner_user_id, 'Demo Store', :slug, 'active',
                'USD', 'en', 'UTC', 'US', 'completed'
            )
            RETURNING id
            """
        ),
        {"owner_user_id": owner_user_id, "slug": slug},
    ).scalar_one()


def _seed_store(conn, email="owner@example.com", slug="demo-store"):
    user_id = _insert_user(conn, email=email)
    store_id = _insert_store(conn, user_id, slug=slug)
    return user_id, store_id


def _insert_category(conn, slug="electronics"):
    return conn.execute(
        text(
            """
            INSERT INTO categories (name, slug)
            VALUES ('Electronics', :slug)
            RETURNING id
            """
        ),
        {"slug": slug},
    ).scalar_one()


def _insert_generation_run(
    conn, store_id, requested_by, requested_count=3, status="queued"
):
    return conn.execute(
        text(
            """
            INSERT INTO generation_runs (
                store_id, requested_by, model_version, input_snapshot,
                requested_count, status
            )
            VALUES (
                :store_id, :requested_by, 'v1', '{}'::jsonb,
                :requested_count, :status
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "requested_by": requested_by,
            "requested_count": requested_count,
            "status": status,
        },
    ).scalar_one()


def _insert_product_idea(
    conn,
    store_id,
    generation_run_id,
    state="new",
    converted_concept_id=None,
):
    return conn.execute(
        text(
            """
            INSERT INTO product_ideas (
                store_id, generation_run_id, name, description, rationale,
                state, converted_concept_id, model_version
            )
            VALUES (
                :store_id, :generation_run_id, 'Idea', 'Description', 'Rationale',
                :state, :converted_concept_id, 'v1'
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "generation_run_id": generation_run_id,
            "state": state,
            "converted_concept_id": converted_concept_id,
        },
    ).scalar_one()


def _insert_idea_evidence(
    conn,
    store_id,
    product_idea_id,
    evidence_type="verified",
    source_url="https://example.com/evidence",
):
    return conn.execute(
        text(
            """
            INSERT INTO idea_evidences (
                store_id, product_idea_id, evidence_type, claim, source_url
            )
            VALUES (
                :store_id, :product_idea_id, :evidence_type, 'Claim', :source_url
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "product_idea_id": product_idea_id,
            "evidence_type": evidence_type,
            "source_url": source_url,
        },
    ).scalar_one()


def _insert_product_concept(
    conn, store_id, created_by, category_id=None, source_idea_id=None
):
    if category_id is None:
        category_id = _insert_category(conn)
    return conn.execute(
        text(
            """
            INSERT INTO product_concepts (
                store_id, source_idea_id, name, category_id, price_minor, cost_minor,
                currency, gross_margin_bp, created_by
            )
            VALUES (
                :store_id, :source_idea_id, 'Concept', :category_id, 1000, 400,
                'USD', 6000, :created_by
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "source_idea_id": source_idea_id,
            "category_id": category_id,
            "created_by": created_by,
        },
    ).scalar_one()


def test_product_ideas_state_check(conn):
    user_id, store_id = _seed_store(conn)
    run_id = _insert_generation_run(conn, store_id, user_id)

    with pytest.raises(DBAPIError):
        _insert_product_idea(conn, store_id, run_id, state="published")


def test_verified_evidence_requires_source_url(conn):
    user_id, store_id = _seed_store(conn)
    run_id = _insert_generation_run(conn, store_id, user_id)
    idea_id = _insert_product_idea(conn, store_id, run_id)

    with pytest.raises(DBAPIError):
        _insert_idea_evidence(
            conn, store_id, idea_id, evidence_type="verified", source_url=None
        )


def test_hypothesis_evidence_allows_no_source_url(conn):
    user_id, store_id = _seed_store(conn)
    run_id = _insert_generation_run(conn, store_id, user_id)
    idea_id = _insert_product_idea(conn, store_id, run_id)

    evidence_id = _insert_idea_evidence(
        conn, store_id, idea_id, evidence_type="hypothesis", source_url=None
    )
    assert evidence_id is not None


def test_generation_run_requested_count_must_be_positive(conn):
    user_id, store_id = _seed_store(conn)

    with pytest.raises(DBAPIError):
        _insert_generation_run(conn, store_id, user_id, requested_count=0)


def test_product_ideas_converted_concept_fk(conn):
    user_id, store_id = _seed_store(conn)
    run_id = _insert_generation_run(conn, store_id, user_id)
    category_id = _insert_category(conn)
    concept_id = _insert_product_concept(
        conn, store_id, user_id, category_id=category_id
    )

    idea_id = _insert_product_idea(
        conn, store_id, run_id, converted_concept_id=concept_id
    )
    assert idea_id is not None

    with pytest.raises(DBAPIError):
        _insert_product_idea(
            conn, store_id, run_id, converted_concept_id=uuid.uuid4()
        )


def test_product_concepts_source_idea_fk(conn):
    user_id, store_id = _seed_store(conn)
    run_id = _insert_generation_run(conn, store_id, user_id)
    idea_id = _insert_product_idea(conn, store_id, run_id)
    category_id = _insert_category(conn)

    concept_id = _insert_product_concept(
        conn, store_id, user_id, category_id=category_id, source_idea_id=idea_id
    )
    assert concept_id is not None

    with pytest.raises(DBAPIError):
        _insert_product_concept(
            conn, store_id, user_id, category_id=category_id, source_idea_id=uuid.uuid4()
        )


def test_product_ideas_updated_at_is_touched(conn):
    user_id, store_id = _seed_store(conn)
    run_id = _insert_generation_run(conn, store_id, user_id)

    idea_id = conn.execute(
        text(
            """
            INSERT INTO product_ideas (
                store_id, generation_run_id, name, description, rationale,
                state, model_version, updated_at
            )
            VALUES (
                :store_id, :run_id, 'Idea', 'Description', 'Rationale',
                'new', 'v1', '2000-01-01T00:00:00Z'
            )
            RETURNING id
            """
        ),
        {"store_id": store_id, "run_id": run_id},
    ).scalar_one()

    conn.execute(
        text("UPDATE product_ideas SET name = 'Changed' WHERE id = :id"),
        {"id": idea_id},
    )

    updated_at = conn.execute(
        text("SELECT updated_at FROM product_ideas WHERE id = :id"),
        {"id": idea_id},
    ).scalar_one()
    assert updated_at > datetime(2000, 1, 1, tzinfo=timezone.utc)
