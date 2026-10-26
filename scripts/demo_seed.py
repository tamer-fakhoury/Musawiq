"""Idempotent Arabic demo seed for the Module 8 feedback loop."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from psycopg.types.json import Jsonb
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

ROOT = Path(__file__).resolve().parents[1]
VAR_DIR = ROOT / "var"
IDS_PATH = VAR_DIR / "demo_ids.json"

USER_ID = uuid.UUID("11111111-1111-4111-8111-000000000001")
STORE_ID = uuid.UUID("22222222-2222-4222-8222-000000000002")
CATEGORY_ID = uuid.UUID("33333333-3333-4333-8333-000000000003")
NICHE_ID = uuid.UUID("44444444-4444-4444-8444-000000000004")
CONCEPT_ID = uuid.UUID("55555555-5555-4555-8555-000000000005")
PROFILE_ID = uuid.UUID("66666666-6666-4666-8666-000000000006")
SEGMENT_ID = uuid.UUID("77777777-7777-4777-8777-000000000007")
TEST_ID = uuid.UUID("88888888-8888-4888-8888-000000000008")
CAMPAIGN_ID = uuid.UUID("99999999-9999-4999-8999-000000000009")
ADSET_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-00000000000a")
VARIATION_IDS = (
    uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-00000000000b"),
    uuid.UUID("cccccccc-cccc-4ccc-8ccc-00000000000c"),
    uuid.UUID("dddddddd-dddd-4ddd-8ddd-00000000000d"),
)

VARIATIONS = (
    ("نسخة الإعلان 1", "عباية جميلة ومريحة"),
    ("نسخة الإعلان 2", "تصميم أنيق يناسبك"),
    ("نسخة الإعلان 3", "خامة ممتازة وعملية"),
)


def _bind(conn: Connection, store_id: uuid.UUID, user_id: uuid.UUID) -> None:
    conn.execute(
        text(f"SET LOCAL app.store_id = '{store_id}'")
    )
    conn.execute(
        text(f"SET LOCAL app.user_id = '{user_id}'")
    )


def _find_or_insert(
    conn: Connection,
    *,
    name: str,
    find_sql: str,
    find_params: dict,
    insert_sql: str,
    insert_params: dict,
) -> tuple[uuid.UUID, bool]:
    row = conn.execute(text(find_sql), find_params).scalar_one_or_none()
    if row is not None:
        return row, False

    row = conn.execute(text(insert_sql), insert_params).scalar_one_or_none()
    if row is not None:
        return row, True

    row = conn.execute(text(find_sql), find_params).scalar_one_or_none()
    if row is None:
        raise RuntimeError(f"could not resolve demo {name}")
    return row, False


def _note(bucket: dict[str, int], name: str) -> None:
    bucket[name] = bucket.get(name, 0) + 1


def _seed(engine: Engine) -> dict:
    inserted: dict[str, int] = {}
    existing: dict[str, int] = {}

    with engine.begin() as conn:
        _bind(conn, STORE_ID, USER_ID)
        user_id, was_inserted = _find_or_insert(
            conn,
            name="user",
            find_sql="SELECT id FROM users WHERE email = :email",
            find_params={"email": "owner@demo.musawiq.local"},
            insert_sql="""
                INSERT INTO users (
                    id, email, full_name, locale, timezone, role, status
                ) VALUES (
                    :id, 'owner@demo.musawiq.local', 'مالك متجر نُور',
                    'ar', 'Asia/Riyadh', 'owner', 'active'
                )
                ON CONFLICT DO NOTHING
                RETURNING id
            """,
            insert_params={"id": USER_ID},
        )
    _note(inserted if was_inserted else existing, "user")

    with engine.begin() as conn:
        _bind(conn, STORE_ID, user_id)
        store_id, was_inserted = _find_or_insert(
            conn,
            name="store",
            find_sql="SELECT id FROM stores WHERE slug = :slug",
            find_params={"slug": "noor-demo"},
            insert_sql="""
                INSERT INTO stores (
                    id, owner_user_id, name, slug, status,
                    default_currency, default_language, timezone,
                    country_code, onboarding_status
                ) VALUES (
                    :id, :owner_user_id, 'متجر نُور', 'noor-demo', 'active',
                    'SAR', 'ar', 'Asia/Riyadh', 'SA', 'completed'
                )
                ON CONFLICT DO NOTHING
                RETURNING id
            """,
            insert_params={"id": STORE_ID, "owner_user_id": user_id},
        )
    _note(inserted if was_inserted else existing, "store")

    with engine.begin() as conn:
        _bind(conn, store_id, user_id)
        category_id, was_inserted = _find_or_insert(
            conn,
            name="category",
            find_sql="""
                SELECT id FROM categories
                WHERE slug = 'abayas' OR name = 'عبايات'
                ORDER BY (slug = 'abayas') DESC, id
                LIMIT 1
            """,
            find_params={},
            insert_sql="""
                INSERT INTO categories (id, name, slug, is_active, sort_order)
                VALUES (:id, 'عبايات', 'abayas', true, 0)
                ON CONFLICT DO NOTHING
                RETURNING id
            """,
            insert_params={"id": CATEGORY_ID},
        )
    _note(inserted if was_inserted else existing, "category")

    with engine.begin() as conn:
        _bind(conn, store_id, user_id)
        niche_id, was_inserted = _find_or_insert(
            conn,
            name="niche",
            find_sql="""
                SELECT id FROM niches
                WHERE store_id = :store_id
                  AND (slug = 'abayas' OR name = 'عبايات')
                ORDER BY (slug = 'abayas') DESC, id
                LIMIT 1
            """,
            find_params={"store_id": store_id},
            insert_sql="""
                INSERT INTO niches (
                    id, category_id, store_id, name, slug, is_active
                ) VALUES (
                    :id, :category_id, :store_id, 'عبايات', 'abayas', true
                )
                ON CONFLICT DO NOTHING
                RETURNING id
            """,
            insert_params={
                "id": NICHE_ID,
                "category_id": category_id,
                "store_id": store_id,
            },
        )
    _note(inserted if was_inserted else existing, "niche")

    with engine.begin() as conn:
        _bind(conn, store_id, user_id)
        concept_id, was_inserted = _find_or_insert(
            conn,
            name="concept",
            find_sql="SELECT id FROM product_concepts WHERE id = :id",
            find_params={"id": CONCEPT_ID},
            insert_sql="""
                INSERT INTO product_concepts (
                    id, store_id, name, description, category_id, niche_id,
                    price_minor, cost_minor, currency, gross_margin_bp,
                    status, version, created_by
                ) VALUES (
                    :id, :store_id, 'عباية صيفية خفيفة',
                    'عباية صيفية خفيفة وأنيقة من قماش مريح للاستخدام اليومي.',
                    :category_id, :niche_id, 24900, 9500, 'SAR', 6185,
                    'draft', 1, :user_id
                )
                ON CONFLICT DO NOTHING
                RETURNING id
            """,
            insert_params={
                "id": CONCEPT_ID,
                "store_id": store_id,
                "category_id": category_id,
                "niche_id": niche_id,
                "user_id": user_id,
            },
        )
    _note(inserted if was_inserted else existing, "concept")

    with engine.begin() as conn:
        _bind(conn, store_id, user_id)
        profile_id, was_inserted = _find_or_insert(
            conn,
            name="audience_profile",
            find_sql="SELECT id FROM audience_profiles WHERE id = :id",
            find_params={"id": PROFILE_ID},
            insert_sql="""
                INSERT INTO audience_profiles (
                    id, store_id, version, status, is_current, niche_ids,
                    languages, notes, created_by
                ) VALUES (
                    :id, :store_id, 1, 'active', true, :niche_ids,
                    :languages,
                    'نساء سعوديات مهتمات بالموضة والعبايات.', :user_id
                )
                ON CONFLICT DO NOTHING
                RETURNING id
            """,
            insert_params={
                "id": PROFILE_ID,
                "store_id": store_id,
                "niche_ids": [niche_id],
                "languages": ["ar"],
                "user_id": user_id,
            },
        )
    _note(inserted if was_inserted else existing, "audience_profile")

    with engine.begin() as conn:
        _bind(conn, store_id, user_id)
        _, was_inserted = _find_or_insert(
            conn,
            name="audience_segment",
            find_sql="SELECT id FROM audience_segments WHERE id = :id",
            find_params={"id": SEGMENT_ID},
            insert_sql="""
                INSERT INTO audience_segments (
                    id, store_id, audience_profile_id, label, locations,
                    age_min, age_max, genders, interests, languages
                ) VALUES (
                    :id, :store_id, :profile_id, 'نساء سعوديات 25-45',
                    :locations, 25, 45, :genders, :interests, :languages
                )
                ON CONFLICT DO NOTHING
                RETURNING id
            """,
            insert_params={
                "id": SEGMENT_ID,
                "store_id": store_id,
                "profile_id": profile_id,
                "locations": Jsonb(["SA"]),
                "genders": ["female"],
                "interests": ["موضة", "عبايات"],
                "languages": ["ar"],
            },
        )
    _note(inserted if was_inserted else existing, "audience_segment")

    with engine.begin() as conn:
        _bind(conn, store_id, user_id)
        test_id, was_inserted = _find_or_insert(
            conn,
            name="test",
            find_sql="SELECT id FROM tests WHERE id = :id",
            find_params={"id": TEST_ID},
            insert_sql="""
                INSERT INTO tests (
                    id, store_id, product_concept_id, name, status,
                    primary_conversion, currency, total_budget_minor,
                    daily_budget_minor, planned_start_at, planned_end_at,
                    created_by
                ) VALUES (
                    :id, :store_id, :concept_id, 'اختبار عباية صيفية', 'draft',
                    'whatsapp_click', 'SAR', 150000, 15000,
                    date_trunc('day', now()),
                    date_trunc('day', now()) + interval '14 days',
                    :user_id
                )
                ON CONFLICT DO NOTHING
                RETURNING id
            """,
            insert_params={
                "id": TEST_ID,
                "store_id": store_id,
                "concept_id": concept_id,
                "user_id": user_id,
            },
        )
    _note(inserted if was_inserted else existing, "test")

    with engine.begin() as conn:
        _bind(conn, store_id, user_id)
        campaign_id, was_inserted = _find_or_insert(
            conn,
            name="campaign",
            find_sql="SELECT id FROM campaigns WHERE id = :id",
            find_params={"id": CAMPAIGN_ID},
            insert_sql="""
                INSERT INTO campaigns (
                    id, store_id, test_id, provider, name, objective, status,
                    budget_type, budget_minor, currency, start_at, end_at,
                    created_by
                ) VALUES (
                    :id, :store_id, :test_id, 'meta', 'حملة عباية صيفية',
                    'traffic', 'draft', 'daily', 15000, 'SAR',
                    date_trunc('day', now()),
                    date_trunc('day', now()) + interval '14 days',
                    :user_id
                )
                ON CONFLICT DO NOTHING
                RETURNING id
            """,
            insert_params={
                "id": CAMPAIGN_ID,
                "store_id": store_id,
                "test_id": test_id,
                "user_id": user_id,
            },
        )
    _note(inserted if was_inserted else existing, "campaign")

    with engine.begin() as conn:
        _bind(conn, store_id, user_id)
        adset_id, was_inserted = _find_or_insert(
            conn,
            name="adset",
            find_sql="SELECT id FROM ad_sets WHERE id = :id",
            find_params={"id": ADSET_ID},
            insert_sql="""
                INSERT INTO ad_sets (
                    id, store_id, campaign_id, name, status, targeting,
                    budget_type, budget_minor, currency, start_at, end_at
                ) VALUES (
                    :id, :store_id, :campaign_id, 'جمهور السعودية', 'draft',
                    :targeting, 'daily', 15000, 'SAR',
                    date_trunc('day', now()),
                    date_trunc('day', now()) + interval '14 days'
                )
                ON CONFLICT DO NOTHING
                RETURNING id
            """,
            insert_params={
                "id": ADSET_ID,
                "store_id": store_id,
                "campaign_id": campaign_id,
                "targeting": Jsonb(
                    {
                        "locations": ["SA"],
                        "age_min": 25,
                        "age_max": 45,
                        "languages": ["ar"],
                    }
                ),
            },
        )
    _note(inserted if was_inserted else existing, "adset")

    variation_ids: list[uuid.UUID] = []
    for variation_id, (name, copy_text) in zip(
        VARIATION_IDS, VARIATIONS
    ):
        with engine.begin() as conn:
            _bind(conn, store_id, user_id)
            resolved_id, was_inserted = _find_or_insert(
                conn,
                name="ad_variation",
                find_sql="SELECT id FROM ad_variations WHERE id = :id",
                find_params={"id": variation_id},
                insert_sql="""
                    INSERT INTO ad_variations (
                        id, store_id, adset_id, name, copy_text,
                        destination_url, status
                    ) VALUES (
                        :id, :store_id, :adset_id, :name, :copy_text,
                        'https://demo.musawiq.local/abaya', 'draft'
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING id
                """,
                insert_params={
                    "id": variation_id,
                    "store_id": store_id,
                    "adset_id": adset_id,
                    "name": name,
                    "copy_text": copy_text,
                },
            )
        variation_ids.append(resolved_id)
        _note(inserted if was_inserted else existing, "ad_variation")

    payload = {
        "store_id": str(store_id),
        "user_id": str(user_id),
        "concept_id": str(concept_id),
        "campaign_id": str(campaign_id),
        "adset_id": str(adset_id),
        "variation_ids": [str(value) for value in variation_ids],
    }

    VAR_DIR.mkdir(parents=True, exist_ok=True)
    IDS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Demo seed complete")
    print(f"inserted: {inserted}")
    print(f"existing: {existing}")
    print(f"ids: {json.dumps(payload, ensure_ascii=False)}")
    print(f"written: {IDS_PATH.relative_to(ROOT)}")
    if not any(inserted.values()):
        print("No new rows.")

    return payload


def main() -> int:
    load_dotenv(ROOT / ".env")
    database_url = os.getenv("MUSAWIQ_DATABASE_URL")
    if not database_url:
        print(
            "FAIL: MUSAWIQ_DATABASE_URL is not set", file=sys.stderr
        )
        return 1

    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    try:
        _seed(engine)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
