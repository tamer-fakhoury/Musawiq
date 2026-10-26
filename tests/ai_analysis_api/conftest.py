"""Fixtures for analysis API tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from musawiq.api.app import create_app
from musawiq.api.routers.analyses import router as analyses_router
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine
from scripts.seed_dev import scratch_database

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Seed:
    store_id: uuid.UUID
    user_id: uuid.UUID
    other_store_id: uuid.UUID
    other_user_id: uuid.UUID
    campaign_id: uuid.UUID


@pytest.fixture(scope="session")
def migrated_url() -> Iterator[str]:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.skip("MUSAWIQ_ADMIN_DATABASE_URL is not set")
    with scratch_database(admin_url) as url:
        yield url


def _seed(url: str) -> Seed:
    store_id, other_store_id = uuid.uuid4(), uuid.uuid4()
    user_id, other_user_id = uuid.uuid4(), uuid.uuid4()
    category_id, concept_id, test_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    campaign_id, adset_id, variation_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    profile_id, segment_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(timezone.utc)

    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            for tenant_user, email in (
                (user_id, f"analysis-{user_id.hex}@dev.local"),
                (other_user_id, f"analysis-{other_user_id.hex}@dev.local"),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO users (id, email, full_name, role, status)
                        VALUES (:id, :email, 'Analysis Owner', 'owner', 'active')
                        """
                    ),
                    {"id": tenant_user, "email": email},
                )
            for tenant_store, owner, name in (
                (store_id, user_id, "Analysis Store"),
                (other_store_id, other_user_id, "Other Analysis Store"),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO stores (
                            id, owner_user_id, name, slug, status,
                            default_currency, default_language, timezone,
                            country_code, onboarding_status
                        ) VALUES (
                            :id, :owner, :name, :slug, 'active',
                            'USD', 'en', 'UTC', 'US', 'completed'
                        )
                        """
                    ),
                    {
                        "id": tenant_store,
                        "owner": owner,
                        "name": name,
                        "slug": f"analysis-{tenant_store.hex}",
                    },
                )

            conn.execute(
                text(
                    """
                    INSERT INTO categories (id, name, slug, is_active, sort_order)
                    VALUES (:id, 'Analysis Category', :slug, true, 10)
                    """
                ),
                {"id": category_id, "slug": f"category-{category_id.hex}"},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO product_concepts (
                        id, store_id, name, description, category_id,
                        price_minor, cost_minor, currency, gross_margin_bp,
                        created_by
                    ) VALUES (
                        :id, :store, 'Concept', 'Concept description', :category,
                        5000, 2500, 'USD', 5000, :user
                    )
                    """
                ),
                {
                    "id": concept_id,
                    "store": store_id,
                    "category": category_id,
                    "user": user_id,
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
                        :id, :store, :concept, 'Test', 'draft', 'cod_order',
                        'USD', 100000, 10000, :start, :end, :user
                    )
                    """
                ),
                {
                    "id": test_id,
                    "store": store_id,
                    "concept": concept_id,
                    "start": now - timedelta(days=1),
                    "end": now + timedelta(days=7),
                    "user": user_id,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO campaigns (
                        id, store_id, test_id, provider, name, objective,
                        status, budget_type, budget_minor, currency,
                        start_at, end_at, created_by
                    ) VALUES (
                        :id, :store, :test, 'meta', 'Campaign', 'conversions',
                        'active', 'daily', 10000, 'USD', :start, :end, :user
                    )
                    """
                ),
                {
                    "id": campaign_id,
                    "store": store_id,
                    "test": test_id,
                    "start": now - timedelta(days=1),
                    "end": now + timedelta(days=7),
                    "user": user_id,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO ad_sets (
                        id, store_id, campaign_id, name, status, targeting,
                        budget_type, budget_minor, currency, start_at, end_at
                    ) VALUES (
                        :id, :store, :campaign, 'Ad set', 'active', :targeting,
                        'daily', 10000, 'USD', :start, :end
                    )
                    """
                ),
                {
                    "id": adset_id,
                    "store": store_id,
                    "campaign": campaign_id,
                    "targeting": Jsonb(
                        {"locations": ["SA"], "age_min": 18, "age_max": 45}
                    ),
                    "start": now - timedelta(days=1),
                    "end": now + timedelta(days=7),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO ad_variations (
                        id, store_id, adset_id, headline, copy_text,
                        destination_url, status
                    ) VALUES (
                        :id, :store, :adset, 'Headline', 'Copy text',
                        'https://example.com', 'draft'
                    )
                    """
                ),
                {"id": variation_id, "store": store_id, "adset": adset_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO audience_profiles (
                        id, store_id, version, status, is_current, languages,
                        created_by
                    ) VALUES (
                        :id, :store, 1, 'active', true, ARRAY['ar'], :user
                    )
                    """
                ),
                {"id": profile_id, "store": store_id, "user": user_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO audience_segments (
                        id, store_id, audience_profile_id, label, locations,
                        age_min, age_max
                    ) VALUES (
                        :id, :store, :profile, 'Segment',
                        '["SA", "AE"]'::jsonb, 18, 45
                    )
                    """
                ),
                {"id": segment_id, "store": store_id, "profile": profile_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO metric_snapshots (
                        store_id, test_id, provider, campaign_id, adset_id,
                        ad_variation_id, period_start, period_end, snapshot_at,
                        currency, spend_minor, impressions, reach, clicks, ctr,
                        cpc_minor, cpm_minor, platform_conversions,
                        cost_per_conversion_minor
                    ) VALUES (
                        :store, :test, 'meta', :campaign, :adset, :variation,
                        :start, :end, :end, 'USD', 10000, 10000, 8000, 200,
                        0.02, 50, 1000, 5, 2000
                    )
                    """
                ),
                {
                    "store": store_id,
                    "test": test_id,
                    "campaign": campaign_id,
                    "adset": adset_id,
                    "variation": variation_id,
                    "start": now - timedelta(days=6),
                    "end": now - timedelta(days=5),
                },
            )
    finally:
        engine.dispose()

    return Seed(
        store_id=store_id,
        user_id=user_id,
        other_store_id=other_store_id,
        other_user_id=other_user_id,
        campaign_id=campaign_id,
    )


@pytest.fixture(scope="session")
def seed(migrated_url: str) -> Seed:
    return _seed(migrated_url)


@pytest.fixture()
def db_engine(migrated_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def clean_analyses(seed: Seed, db_engine: Engine) -> Iterator[None]:
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM ai_analyses WHERE store_id = :store_id"),
            {"store_id": seed.store_id},
        )
    yield


@pytest.fixture()
def client(migrated_url: str, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", migrated_url)
    get_settings.cache_clear()
    dispose_engine()
    app = create_app()
    app.include_router(analyses_router)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        dispose_engine()
        get_settings.cache_clear()


def headers(seed: Seed, *, other: bool = False) -> dict[str, str]:
    store = seed.other_store_id if other else seed.store_id
    user = seed.other_user_id if other else seed.user_id
    return {
        "X-Store-Id": str(store),
        "X-User-Id": str(user),
        "X-User-Role": "owner",
    }
