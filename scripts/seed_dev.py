"""Deterministic, idempotent development seed for Musawiq.

Safety:
    The seed refuses to run unless ``MUSAWIQ_SEED_ENV=development`` and
    ``MUSAWIQ_APP_ENV`` is not ``production``.

Modes:
    --scratch   create a throwaway database from ``MUSAWIQ_ADMIN_DATABASE_URL``,
                migrate to head, seed, report, then drop it (default)
    --url DSN   seed an existing migrated database

Every row has a fixed UUID and is inserted with ``ON CONFLICT DO NOTHING``, so
running the seed repeatedly leaves exactly one copy of each row. No credentials
or real personal data are seeded.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from scripts.gen_schema_docs import ROOT, libpq_url, quote_ident, with_database

load_dotenv(ROOT / ".env")

SEED_TIMESTAMP = "2026-01-01 00:00:00+00"

OWNER_ID = "11111111-1111-4111-8111-111111111111"
MANAGER_ID = "22222222-2222-4222-8222-222222222222"
ANALYST_ID = "33333333-3333-4333-8333-333333333333"
STORE_ID = "44444444-4444-4444-8444-444444444444"
CATEGORY_ROOT_ID = "55555555-5555-4555-8555-555555555551"
CATEGORY_CHILD_ID = "55555555-5555-4555-8555-555555555552"
NICHE_GLOBAL_ID = "66666666-6666-4666-8666-666666666661"
NICHE_STORE_ID = "66666666-6666-4666-8666-666666666662"
SCORING_PLATFORM_ID = "77777777-7777-4777-8777-777777777771"
SCORING_STORE_ID = "77777777-7777-4777-8777-777777777772"
DECISION_PLATFORM_ID = "88888888-8888-4888-8888-888888888881"
OPTIMIZATION_GLOBAL_ID = "99999999-9999-4999-8999-999999999991"
AUDIENCE_PROFILE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
SEGMENT_PROFESSIONALS_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
SEGMENT_FAMILIES_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2"

SUMMARY_ORDER = (
    "users",
    "stores",
    "categories",
    "niches",
    "scoring_models",
    "decision_rule_sets",
    "optimization_rule_sets",
    "audience_profiles",
    "audience_segments",
)


class SeedRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class SeedItem:
    label: str
    inserted: int
    skipped: int
    note: str = ""


@dataclass(frozen=True)
class SeedResult:
    items: tuple[SeedItem, ...]

    @property
    def total_inserted(self) -> int:
        return sum(item.inserted for item in self.items)

    @property
    def total_skipped(self) -> int:
        return sum(item.skipped for item in self.items)


def environment_error() -> str | None:
    seed_env = os.getenv("MUSAWIQ_SEED_ENV", "").strip().lower()
    app_env = os.getenv("MUSAWIQ_APP_ENV", "").strip().lower()
    if seed_env != "development":
        return "MUSAWIQ_SEED_ENV must be 'development'"
    if app_env == "production":
        return "MUSAWIQ_APP_ENV must not be 'production'"
    return None


def require_development() -> None:
    error = environment_error()
    if error:
        raise SeedRefused(error)


def build_result(
    counts: dict[str, list[int]], notes: dict[str, str]
) -> SeedResult:
    items = []
    for label in SUMMARY_ORDER:
        inserted, skipped = counts.get(label, [0, 0])
        items.append(
            SeedItem(
                label=label,
                inserted=inserted,
                skipped=skipped,
                note=notes.get(label, ""),
            )
        )
    return SeedResult(items=tuple(items))


def seed_database(url: str) -> SeedResult:
    require_development()

    counts: dict[str, list[int]] = {}
    notes: dict[str, str] = {}

    with psycopg.connect(libpq_url(url)) as conn:
        with conn.cursor() as cur:

            def insert(label: str, sql: str, params: tuple = ()) -> None:
                cur.execute(sql, params)
                inserted = 1 if cur.rowcount == 1 else 0
                entry = counts.setdefault(label, [0, 0])
                entry[0] += inserted
                entry[1] += 1 - inserted

            # Users -----------------------------------------------------------
            users = (
                (OWNER_ID, "owner@dev.musawiq.local", "Dev Owner", "owner"),
                (MANAGER_ID, "manager@dev.musawiq.local", "Dev Manager", "manager"),
                (ANALYST_ID, "analyst@dev.musawiq.local", "Dev Analyst", "analyst"),
            )
            for user_id, email, full_name, role in users:
                insert(
                    "users",
                    """
                    INSERT INTO public.users (
                        id, email, password_hash, full_name, phone, locale,
                        timezone, role, status, email_verified_at,
                        auth_provider, auth_subject, created_at, updated_at
                    ) VALUES (
                        %s, %s, NULL, %s, NULL, 'ar', 'Asia/Riyadh', %s,
                        'active', %s::timestamptz, NULL, NULL,
                        %s::timestamptz, %s::timestamptz
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        user_id,
                        email,
                        full_name,
                        role,
                        SEED_TIMESTAMP,
                        SEED_TIMESTAMP,
                        SEED_TIMESTAMP,
                    ),
                )

            # Store -----------------------------------------------------------
            insert(
                "stores",
                """
                INSERT INTO public.stores (
                    id, owner_user_id, name, slug, status, default_currency,
                    default_language, timezone, country_code, onboarding_status,
                    settings, created_at, updated_at
                ) VALUES (
                    %s, %s, 'Dev Store', 'dev-store', 'active', 'SAR', 'ar',
                    'Asia/Riyadh', 'SA', 'completed', %s,
                    %s::timestamptz, %s::timestamptz
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    STORE_ID,
                    OWNER_ID,
                    Jsonb({"schema_version": 1, "seed": "dev"}),
                    SEED_TIMESTAMP,
                    SEED_TIMESTAMP,
                ),
            )

            # Taxonomy --------------------------------------------------------
            insert(
                "categories",
                """
                INSERT INTO public.categories (
                    id, parent_id, name, slug, is_active, sort_order,
                    created_at, updated_at
                ) VALUES (
                    %s, NULL, 'Home & Kitchen', 'home-kitchen', true, 10,
                    %s::timestamptz, %s::timestamptz
                )
                ON CONFLICT DO NOTHING
                """,
                (CATEGORY_ROOT_ID, SEED_TIMESTAMP, SEED_TIMESTAMP),
            )
            insert(
                "categories",
                """
                INSERT INTO public.categories (
                    id, parent_id, name, slug, is_active, sort_order,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, 'Kitchen Gadgets', 'kitchen-gadgets', true, 10,
                    %s::timestamptz, %s::timestamptz
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    CATEGORY_CHILD_ID,
                    CATEGORY_ROOT_ID,
                    SEED_TIMESTAMP,
                    SEED_TIMESTAMP,
                ),
            )
            insert(
                "niches",
                """
                INSERT INTO public.niches (
                    id, category_id, store_id, name, slug, is_active,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, NULL, 'Coffee & Tea', 'coffee-tea', true,
                    %s::timestamptz, %s::timestamptz
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    NICHE_GLOBAL_ID,
                    CATEGORY_CHILD_ID,
                    SEED_TIMESTAMP,
                    SEED_TIMESTAMP,
                ),
            )
            insert(
                "niches",
                """
                INSERT INTO public.niches (
                    id, category_id, store_id, name, slug, is_active,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, 'Home Barista', 'home-barista', true,
                    %s::timestamptz, %s::timestamptz
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    NICHE_STORE_ID,
                    CATEGORY_CHILD_ID,
                    STORE_ID,
                    SEED_TIMESTAMP,
                    SEED_TIMESTAMP,
                ),
            )

            # Scoring models --------------------------------------------------
            insert(
                "scoring_models",
                """
                INSERT INTO public.scoring_models (
                    id, store_id, key, version, name, description, weights,
                    parameters, is_active, effective_from, created_at, updated_at
                ) VALUES (
                    %s, NULL, 'default', 1, 'Default Scoring Model',
                    'Platform default development scoring model.', %s, %s, true,
                    %s::timestamptz, %s::timestamptz, %s::timestamptz
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    SCORING_PLATFORM_ID,
                    Jsonb(
                        {
                            "schema_version": 1,
                            "demand": 0.4,
                            "margin": 0.3,
                            "audience_fit": 0.2,
                            "competition": 0.1,
                        }
                    ),
                    Jsonb({"schema_version": 1, "scale": 100}),
                    SEED_TIMESTAMP,
                    SEED_TIMESTAMP,
                    SEED_TIMESTAMP,
                ),
            )
            insert(
                "scoring_models",
                """
                INSERT INTO public.scoring_models (
                    id, store_id, key, version, name, description, weights,
                    parameters, is_active, effective_from, created_at, updated_at
                ) VALUES (
                    %s, %s, 'dev-store', 1, 'Dev Store Scoring Model',
                    'Store-specific development scoring model.', %s, %s, true,
                    %s::timestamptz, %s::timestamptz, %s::timestamptz
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    SCORING_STORE_ID,
                    STORE_ID,
                    Jsonb(
                        {
                            "schema_version": 1,
                            "demand": 0.35,
                            "margin": 0.35,
                            "audience_fit": 0.2,
                            "competition": 0.1,
                        }
                    ),
                    Jsonb({"schema_version": 1, "scale": 100}),
                    SEED_TIMESTAMP,
                    SEED_TIMESTAMP,
                    SEED_TIMESTAMP,
                ),
            )

            # Platform decision and optimization defaults (future tables) ----
            cur.execute(
                "SELECT to_regclass('public.decision_rule_sets') IS NOT NULL"
            )
            if not cur.fetchone()[0]:
                notes["decision_rule_sets"] = "SKIPPED: table not present at this head"
            else:
                insert(
                    "decision_rule_sets",
                    """
                    INSERT INTO public.decision_rule_sets (
                        id, store_id, category_id, version, is_active,
                        min_spend_minor, min_clicks, min_conversions,
                        min_confirmed_deposits, min_conversion_rate,
                        max_cost_per_conversion_minor, rules, created_by,
                        created_at, updated_at
                    ) VALUES (
                        %s, NULL, NULL, 1, true, 0, 0, 0, 0, 0, 0, %s, %s,
                        %s::timestamptz, %s::timestamptz
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        DECISION_PLATFORM_ID,
                        Jsonb(
                            {
                                "schema_version": 1,
                                "seed": "dev",
                                "notes": "platform default",
                            }
                        ),
                        OWNER_ID,
                        SEED_TIMESTAMP,
                        SEED_TIMESTAMP,
                    ),
                )

            cur.execute(
                "SELECT to_regclass('public.optimization_rule_sets') IS NOT NULL"
            )
            if not cur.fetchone()[0]:
                notes["optimization_rule_sets"] = (
                    "SKIPPED: table not present at this head"
                )
            else:
                insert(
                    "optimization_rule_sets",
                    """
                    INSERT INTO public.optimization_rule_sets (
                        id, store_id, scope, campaign_id, version, is_active,
                        min_impressions, min_clicks, min_conversions, ctr_floor,
                        cpc_ceiling_minor, cost_per_conversion_ceiling_minor,
                        rules, created_by, created_at, updated_at
                    ) VALUES (
                        %s, NULL, 'global', NULL, 1, true, 0, 0, 0, 0, 0, 0,
                        %s, %s, %s::timestamptz, %s::timestamptz
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        OPTIMIZATION_GLOBAL_ID,
                        Jsonb(
                            {
                                "schema_version": 1,
                                "seed": "dev",
                                "notes": "global default",
                            }
                        ),
                        OWNER_ID,
                        SEED_TIMESTAMP,
                        SEED_TIMESTAMP,
                    ),
                )

            # Audience profile and segments -----------------------------------
            insert(
                "audience_profiles",
                """
                INSERT INTO public.audience_profiles (
                    id, store_id, version, status, is_current, niche_ids,
                    languages, notes, created_by, created_at, updated_at
                ) VALUES (
                    %s, %s, 1, 'active', true, ARRAY[%s, %s]::uuid[],
                    ARRAY['ar']::text[], 'Development audience profile.', %s,
                    %s::timestamptz, %s::timestamptz
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    AUDIENCE_PROFILE_ID,
                    STORE_ID,
                    NICHE_GLOBAL_ID,
                    NICHE_STORE_ID,
                    OWNER_ID,
                    SEED_TIMESTAMP,
                    SEED_TIMESTAMP,
                ),
            )
            segments = (
                (
                    SEGMENT_PROFESSIONALS_ID,
                    "Young Professionals",
                    Jsonb(
                        [
                            {
                                "schema_version": 1,
                                "country": "SA",
                                "city": "Riyadh",
                            }
                        ]
                    ),
                    25,
                    40,
                    ["female", "male"],
                    ["coffee", "home"],
                ),
                (
                    SEGMENT_FAMILIES_ID,
                    "Families",
                    Jsonb(
                        [
                            {
                                "schema_version": 1,
                                "country": "SA",
                                "city": "Jeddah",
                            }
                        ]
                    ),
                    30,
                    50,
                    ["female", "male"],
                    ["family", "home"],
                ),
            )
            for (
                segment_id,
                label,
                locations,
                age_min,
                age_max,
                genders,
                interests,
            ) in segments:
                insert(
                    "audience_segments",
                    """
                    INSERT INTO public.audience_segments (
                        id, store_id, audience_profile_id, label, locations,
                        age_min, age_max, genders, interests, languages,
                        created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        ARRAY['ar']::text[], %s::timestamptz
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        segment_id,
                        STORE_ID,
                        AUDIENCE_PROFILE_ID,
                        label,
                        locations,
                        age_min,
                        age_max,
                        genders,
                        interests,
                        SEED_TIMESTAMP,
                    ),
                )

    return build_result(counts, notes)


def print_summary(result: SeedResult) -> None:
    print("SEED SUMMARY")
    print(f"{'Item':<28}{'Inserted':>10}{'Skipped':>10}  Note")
    print("-" * 78)
    for item in result.items:
        print(
            f"{item.label:<28}{item.inserted:>10}{item.skipped:>10}  {item.note}"
        )
    print("-" * 78)
    print(
        f"{'TOTAL':<28}{result.total_inserted:>10}{result.total_skipped:>10}"
    )


@contextmanager
def scratch_database(admin_url: str) -> Iterator[str]:
    scratch = f"musawiq_seed_dev_{uuid.uuid4().hex[:10]}"
    scratch_url = with_database(admin_url, scratch)
    admin = psycopg.connect(libpq_url(admin_url), autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(f"CREATE DATABASE {quote_ident(scratch)}")
        print(f"created scratch database: {scratch}", file=sys.stderr)

        env = os.environ.copy()
        env["MUSAWIQ_DATABASE_URL"] = scratch_url
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        yield scratch_url
    finally:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {quote_ident(scratch)} WITH (FORCE)")
        admin.close()
        print(f"dropped scratch database: {scratch}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--scratch",
        action="store_true",
        help="create a throwaway database from MUSAWIQ_ADMIN_DATABASE_URL (default)",
    )
    group.add_argument(
        "--url",
        help="seed an existing migrated database instead of creating a scratch one",
    )
    args = parser.parse_args(argv)

    error = environment_error()
    if error:
        print(f"REFUSED: {error}", file=sys.stderr)
        print(
            "Set MUSAWIQ_SEED_ENV=development and do not set "
            "MUSAWIQ_APP_ENV=production.",
            file=sys.stderr,
        )
        return 1

    try:
        if args.url:
            result = seed_database(args.url)
        else:
            admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
            if not admin_url:
                print(
                    "FAIL: MUSAWIQ_ADMIN_DATABASE_URL is not set",
                    file=sys.stderr,
                )
                return 1
            with scratch_database(admin_url) as url:
                result = seed_database(url)
    except SeedRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
