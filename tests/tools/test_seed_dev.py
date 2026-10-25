"""Tests for the deterministic development seed."""

from __future__ import annotations

import os

import psycopg
import pytest

from scripts import seed_dev
from scripts.gen_schema_docs import libpq_url


def _counts(url: str) -> dict[str, int]:
    queries = {
        "users": "SELECT count(*) FROM public.users",
        "owner_users": (
            "SELECT count(*) FROM public.users "
            "WHERE email = 'owner@dev.musawiq.local'"
        ),
        "stores": "SELECT count(*) FROM public.stores",
        "dev_store": (
            "SELECT count(*) FROM public.stores WHERE slug = 'dev-store'"
        ),
        "categories": "SELECT count(*) FROM public.categories",
        "niches": "SELECT count(*) FROM public.niches",
        "scoring_models": "SELECT count(*) FROM public.scoring_models",
        "decision_rule_sets": "SELECT count(*) FROM public.decision_rule_sets",
        "decision_platform": (
            "SELECT count(*) FROM public.decision_rule_sets "
            "WHERE store_id IS NULL AND category_id IS NULL AND version = 1"
        ),
        "decision_store": (
            "SELECT count(*) FROM public.decision_rule_sets "
            "WHERE store_id = '44444444-4444-4444-8444-444444444444'::uuid "
            "AND category_id IS NULL AND version = 1"
        ),
        "optimization_rule_sets": (
            "SELECT count(*) FROM public.optimization_rule_sets"
        ),
        "optimization_global": (
            "SELECT count(*) FROM public.optimization_rule_sets "
            "WHERE store_id IS NULL AND scope = 'global' "
            "AND campaign_id IS NULL AND version = 1"
        ),
        "optimization_store": (
            "SELECT count(*) FROM public.optimization_rule_sets "
            "WHERE store_id = '44444444-4444-4444-8444-444444444444'::uuid "
            "AND scope = 'store' AND campaign_id IS NULL AND version = 1"
        ),
        "audience_profiles": "SELECT count(*) FROM public.audience_profiles",
        "audience_segments": "SELECT count(*) FROM public.audience_segments",
    }
    with psycopg.connect(libpq_url(url)) as conn, conn.cursor() as cur:
        result = {}
        for label, sql in queries.items():
            cur.execute(sql)
            result[label] = cur.fetchone()[0]
    return result


def test_seed_twice_is_idempotent(monkeypatch) -> None:
    monkeypatch.setenv("MUSAWIQ_SEED_ENV", "development")
    monkeypatch.delenv("MUSAWIQ_APP_ENV", raising=False)

    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.fail("MUSAWIQ_ADMIN_DATABASE_URL is not set; cannot create scratch DB")

    with seed_dev.scratch_database(admin_url) as url:
        first = seed_dev.seed_database(url)
        first_counts = _counts(url)

        second = seed_dev.seed_database(url)
        second_counts = _counts(url)

        with psycopg.connect(libpq_url(url)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT role, status FROM public.users "
                "WHERE email = 'owner@dev.musawiq.local'"
            )
            owner = cur.fetchone()

    assert first.total_inserted == 17
    assert second.total_inserted == 0
    assert second.total_skipped == 17
    assert first_counts == second_counts
    assert first_counts["users"] == 3
    assert first_counts["owner_users"] == 1
    assert first_counts["stores"] == 1
    assert first_counts["dev_store"] == 1
    assert first_counts["categories"] == 2
    assert first_counts["niches"] == 2
    assert first_counts["scoring_models"] == 2
    assert first_counts["decision_rule_sets"] == 2
    assert first_counts["decision_platform"] == 1
    assert first_counts["decision_store"] == 1
    assert first_counts["optimization_rule_sets"] == 2
    assert first_counts["optimization_global"] == 1
    assert first_counts["optimization_store"] == 1
    assert first_counts["audience_profiles"] == 1
    assert first_counts["audience_segments"] == 2
    assert owner == ("owner", "active")

    first_items = {item.label: item for item in first.items}
    second_items = {item.label: item for item in second.items}
    for label, count in (
        ("decision_rule_sets", 2),
        ("optimization_rule_sets", 2),
    ):
        assert first_items[label].inserted == count
        assert first_items[label].skipped == 0
        assert first_items[label].note == ""
        assert second_items[label].inserted == 0
        assert second_items[label].skipped == count


def test_refuses_without_seed_environment(monkeypatch, capsys) -> None:
    monkeypatch.delenv("MUSAWIQ_SEED_ENV", raising=False)
    monkeypatch.delenv("MUSAWIQ_APP_ENV", raising=False)

    result = seed_dev.main(["--url", "postgresql://127.0.0.1:1/missing"])

    assert result == 1
    error = capsys.readouterr().err
    assert "REFUSED" in error
    assert "MUSAWIQ_SEED_ENV" in error


def test_refuses_in_production(monkeypatch, capsys) -> None:
    monkeypatch.setenv("MUSAWIQ_SEED_ENV", "development")
    monkeypatch.setenv("MUSAWIQ_APP_ENV", "production")

    result = seed_dev.main(["--url", "postgresql://127.0.0.1:1/missing"])

    assert result == 1
    error = capsys.readouterr().err
    assert "REFUSED" in error
    assert "production" in error
