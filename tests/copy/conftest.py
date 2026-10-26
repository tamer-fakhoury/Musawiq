"""Fixtures for AI copy suggestion tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from musawiq.api.app import create_app
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine
from scripts.seed_dev import scratch_database


@dataclass(frozen=True)
class CopyContext:
    store_id: uuid.UUID
    user_id: uuid.UUID
    campaign_id: uuid.UUID
    adset_id: uuid.UUID


@pytest.fixture(scope="session")
def migrated_url() -> Iterator[str]:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.skip("MUSAWIQ_ADMIN_DATABASE_URL is not set")
    with scratch_database(admin_url) as url:
        yield url


@pytest.fixture(scope="session")
def db_engine(migrated_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def copy_context(db_engine: Engine) -> CopyContext:
    store_id = uuid.uuid4()
    user_id = uuid.uuid4()
    category_id = uuid.uuid4()
    concept_id = uuid.uuid4()
    test_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    adset_id = uuid.uuid4()
    variation_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:12]

    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (id, email, full_name, role, status)
                VALUES (:id, :email, 'Copy Test Owner', 'owner', 'active')
                """
            ),
            {"id": user_id, "email": f"copy-{suffix}@example.com"},
        )
        conn.execute(
            text(
                """
                INSERT INTO stores (
                    id, owner_user_id, name, slug, status,
                    default_currency, default_language, timezone, country_code,
                    onboarding_status
                ) VALUES (
                    :id, :owner_user_id, 'Copy Test Store', :slug, 'active',
                    'USD', 'en', 'UTC', 'US', 'completed'
                )
                """
            ),
            {
                "id": store_id,
                "owner_user_id": user_id,
                "slug": f"copy-{suffix}",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO categories (id, name, slug, is_active, sort_order)
                VALUES (:id, 'Copy Test', :slug, true, 1)
                """
            ),
            {"id": category_id, "slug": f"copy-{suffix}"},
        )
        conn.execute(
            text(
                """
                INSERT INTO product_concepts (
                    id, store_id, name, description, category_id, price_minor,
                    cost_minor, currency, gross_margin_bp, created_by
                ) VALUES (
                    :id, :store_id, 'Arabic Coffee', 'Specialty coffee beans',
                    :category_id, 4500, 2000, 'USD', 5555, :created_by
                )
                """
            ),
            {
                "id": concept_id,
                "store_id": store_id,
                "category_id": category_id,
                "created_by": user_id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO tests (
                    id, store_id, product_concept_id, name, status,
                    primary_conversion, currency, total_budget_minor,
                    daily_budget_minor, planned_start_at, planned_end_at,
                    created_by
                ) VALUES (
                    :id, :store_id, :concept_id, 'Copy Test', 'draft',
                    'whatsapp_click', 'USD', 100000, 10000,
                    now(), now() + interval '30 days', :created_by
                )
                """
            ),
            {
                "id": test_id,
                "store_id": store_id,
                "concept_id": concept_id,
                "created_by": user_id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO audience_profiles (
                    id, store_id, version, status, is_current, niche_ids,
                    languages, notes, created_by
                ) VALUES (
                    :id, :store_id, 1, 'active', true, '{}'::uuid[],
                    ARRAY['ar']::text[], 'Copy test audience', :created_by
                )
                """
            ),
            {
                "id": profile_id,
                "store_id": store_id,
                "created_by": user_id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO audience_segments (
                    store_id, audience_profile_id, label, locations,
                    age_min, age_max, interests, languages
                ) VALUES (
                    :store_id, :profile_id, 'Saudi shoppers', :locations,
                    18, 45, ARRAY['coffee']::text[], ARRAY['ar']::text[]
                )
                """
            ),
            {
                "store_id": store_id,
                "profile_id": profile_id,
                "locations": Jsonb(["SA", "AE"]),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO campaigns (
                    id, store_id, test_id, provider, name, objective, status,
                    budget_type, budget_minor, currency, start_at, end_at,
                    created_by
                ) VALUES (
                    :id, :store_id, :test_id, 'meta', 'Copy Campaign',
                    'conversions', 'draft', 'daily', 5000, 'USD',
                    now(), now() + interval '7 days', :created_by
                )
                """
            ),
            {
                "id": campaign_id,
                "store_id": store_id,
                "test_id": test_id,
                "created_by": user_id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO ad_sets (
                    id, store_id, campaign_id, name, status, targeting,
                    currency, start_at, end_at
                ) VALUES (
                    :id, :store_id, :campaign_id, 'Saudi audience', 'draft',
                    :targeting, 'USD', now(), now() + interval '7 days'
                )
                """
            ),
            {
                "id": adset_id,
                "store_id": store_id,
                "campaign_id": campaign_id,
                "targeting": Jsonb(
                    {
                        "locations": ["SA"],
                        "age_min": 18,
                        "age_max": 45,
                        "languages": ["ar"],
                    }
                ),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO ad_variations (
                    id, store_id, adset_id, copy_text, headline,
                    destination_url, status
                ) VALUES (
                    :id, :store_id, :adset_id, 'قهوة مختصة تصلك حتى بابك',
                    'عرض اليوم', 'https://example.test/offer', 'draft'
                )
                """
            ),
            {
                "id": variation_id,
                "store_id": store_id,
                "adset_id": adset_id,
            },
        )

    return CopyContext(
        store_id=store_id,
        user_id=user_id,
        campaign_id=campaign_id,
        adset_id=adset_id,
    )


@pytest.fixture()
def client(migrated_url: str, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", migrated_url)
    get_settings.cache_clear()
    dispose_engine()

    app = create_app()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        dispose_engine()
        get_settings.cache_clear()
