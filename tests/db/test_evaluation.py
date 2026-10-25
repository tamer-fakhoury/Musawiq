"""Product evaluation tables: constraints and append-only behavior (DB-0.7)."""

from __future__ import annotations

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


def _insert_product_concept(conn, store_id, created_by, category_id=None, status="draft"):
    if category_id is None:
        category_id = _insert_category(conn)
    return conn.execute(
        text(
            """
            INSERT INTO product_concepts (
                store_id, name, category_id, price_minor, cost_minor, currency,
                gross_margin_bp, status, created_by
            )
            VALUES (
                :store_id, 'Concept', :category_id, 1000, 400, 'USD', 6000,
                :status, :created_by
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "category_id": category_id,
            "status": status,
            "created_by": created_by,
        },
    ).scalar_one()


def _insert_scoring_model(conn, key="default", version=1):
    return conn.execute(
        text(
            """
            INSERT INTO scoring_models (
                key, version, name, weights, effective_from
            )
            VALUES (:key, :version, 'Default Model', '{}'::jsonb, now())
            RETURNING id
            """
        ),
        {"key": key, "version": version},
    ).scalar_one()


def _insert_evaluation(
    conn,
    store_id,
    product_concept_id,
    scoring_model_id,
    confidence="high",
    score=None,
    sufficiency_check_id=None,
):
    return conn.execute(
        text(
            """
            INSERT INTO evaluations (
                store_id, product_concept_id, scoring_model_id, model_version,
                score, confidence, is_reliable, sufficiency_check_id,
                input_snapshot, evaluated_at
            )
            VALUES (
                :store_id, :product_concept_id, :scoring_model_id, 1,
                :score, :confidence, true, :sufficiency_check_id,
                '{}'::jsonb, now()
            )
            RETURNING id
            """
        ),
        {
            "store_id": store_id,
            "product_concept_id": product_concept_id,
            "scoring_model_id": scoring_model_id,
            "score": score,
            "confidence": confidence,
            "sufficiency_check_id": sufficiency_check_id,
        },
    ).scalar_one()


def _insert_score_factor(conn, store_id, evaluation_id):
    return conn.execute(
        text(
            """
            INSERT INTO score_factors (
                store_id, evaluation_id, factor_key, factor_label,
                direction, contribution, explanation
            )
            VALUES (
                :store_id, :evaluation_id, 'demand', 'Demand',
                'positive', 1.5, 'Strong demand'
            )
            RETURNING id
            """
        ),
        {"store_id": store_id, "evaluation_id": evaluation_id},
    ).scalar_one()


def _seed_evaluation(conn):
    user_id, store_id = _seed_store(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id)
    model_id = _insert_scoring_model(conn)
    evaluation_id = _insert_evaluation(conn, store_id, concept_id, model_id)
    return store_id, evaluation_id


def test_evaluations_allow_null_score(conn):
    user_id, store_id = _seed_store(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id)
    model_id = _insert_scoring_model(conn)

    evaluation_id = _insert_evaluation(
        conn, store_id, concept_id, model_id, score=None
    )
    score = conn.execute(
        text("SELECT score FROM evaluations WHERE id = :id"),
        {"id": evaluation_id},
    ).scalar_one()

    assert score is None


def test_product_concepts_status_check(conn):
    user_id, store_id = _seed_store(conn)
    category_id = _insert_category(conn)

    with pytest.raises(DBAPIError):
        conn.execute(
            text(
                """
                INSERT INTO product_concepts (
                    store_id, name, category_id, price_minor, cost_minor, currency,
                    gross_margin_bp, status, created_by
                )
                VALUES (
                    :store_id, 'Concept', :category_id, 1000, 400, 'USD', 6000,
                    'published', :created_by
                )
                """
            ),
            {
                "store_id": store_id,
                "category_id": category_id,
                "created_by": user_id,
            },
        )


def test_evaluations_confidence_check(conn):
    user_id, store_id = _seed_store(conn)
    concept_id = _insert_product_concept(conn, store_id, user_id)
    model_id = _insert_scoring_model(conn)

    with pytest.raises(DBAPIError):
        _insert_evaluation(
            conn, store_id, concept_id, model_id, confidence="certain"
        )


def test_scoring_models_key_version_is_unique(conn):
    _insert_scoring_model(conn, key="default", version=1)

    with pytest.raises(DBAPIError):
        _insert_scoring_model(conn, key="default", version=1)


def test_scoring_models_allow_new_version(conn):
    _insert_scoring_model(conn, key="default", version=1)
    _insert_scoring_model(conn, key="default", version=2)

    count = conn.execute(
        text("SELECT count(*) FROM scoring_models WHERE key = 'default'")
    ).scalar_one()
    assert count == 2


def test_score_factors_reject_update(conn):
    store_id, evaluation_id = _seed_evaluation(conn)
    _insert_score_factor(conn, store_id, evaluation_id)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("UPDATE score_factors SET factor_label = 'Changed'"))


def test_score_factors_reject_delete(conn):
    store_id, evaluation_id = _seed_evaluation(conn)
    _insert_score_factor(conn, store_id, evaluation_id)

    with pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("DELETE FROM score_factors"))
