"""Tests for the foreign-key matrix generator."""

from __future__ import annotations

import os

import psycopg
import pytest

from scripts import fk_matrix
from scripts.gen_schema_docs import libpq_url


@pytest.fixture(scope="module")
def fk_scratch_url() -> str:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.fail("MUSAWIQ_ADMIN_DATABASE_URL is not set; cannot create scratch DB")
    with fk_matrix.scratch_database(admin_url) as url:
        yield url


def test_check_is_green(fk_scratch_url: str, capsys) -> None:
    result = fk_matrix.main(["--url", fk_scratch_url, "--check"])

    assert result == 0
    assert "FK MATRIX OK" in capsys.readouterr().out


def test_candidate_detector_flags_probe_table(fk_scratch_url: str) -> None:
    with psycopg.connect(libpq_url(fk_scratch_url)) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE public.fk_probe_candidate (
                        id uuid PRIMARY KEY DEFAULT uuidv7(),
                        campaign_id uuid
                    )
                    """
                )
            matrix = fk_matrix.build_matrix(conn)
            candidates = {
                (candidate.table, candidate.column): candidate.target_table
                for candidate in matrix.candidates
            }
            assert candidates[("fk_probe_candidate", "campaign_id")] == "campaigns"
        finally:
            conn.rollback()


def test_polymorphic_and_array_columns_are_never_candidates(
    fk_scratch_url: str,
) -> None:
    with psycopg.connect(libpq_url(fk_scratch_url)) as conn:
        matrix = fk_matrix.build_matrix(conn)

    candidate_keys = {(candidate.table, candidate.column) for candidate in matrix.candidates}
    for key in (
        ("audit_logs", "target_id"),
        ("attributions", "subject_id"),
        ("alerts", "related_id"),
        ("events", "event_id"),
        ("audience_profiles", "niche_ids"),
        ("page_versions", "image_file_ids"),
        ("content_generation_jobs", "result_creative_ids"),
    ):
        assert key not in candidate_keys

    assert all(not candidate.type.endswith("[]") for candidate in matrix.candidates)
