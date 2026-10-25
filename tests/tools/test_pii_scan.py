"""Tests for the PII classification scanner.

The green scan uses a real scratch database. The negative detector test creates
a probe table inside a transaction and rolls it back, so nothing leaks into the
shared scratch database.
"""

from __future__ import annotations

import json
import os

import psycopg
import pytest

from scripts import pii_scan
from scripts.gen_schema_docs import ROOT, introspect, libpq_url


@pytest.fixture(scope="module")
def migrated_scratch_url() -> str:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.fail("MUSAWIQ_ADMIN_DATABASE_URL is not set; cannot create scratch DB")
    with pii_scan.scratch_database(admin_url) as url:
        yield url


def test_scratch_scan_is_green(capsys) -> None:
    result = pii_scan.main(["--scratch"])

    assert result == 0
    output = capsys.readouterr().out
    assert "PII SCAN PASS" in output
    assert "heuristic_coverage: PASS" in output


def test_registry_is_documented() -> None:
    docs = (ROOT / "docs" / "PII.md").read_text(encoding="utf-8")
    for table, column in pii_scan.REGISTRY:
        assert f"`{table}.{column}`" in docs


def test_registry_classes_are_valid() -> None:
    for entry in pii_scan.REGISTRY.values():
        assert entry.classification in pii_scan.CLASSES
        assert entry.protection in pii_scan.PROTECTIONS


def test_detector_flags_unclassified_probe_column(migrated_scratch_url: str) -> None:
    with psycopg.connect(libpq_url(migrated_scratch_url)) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE TABLE public.pii_probe_unclassified "
                    "(email text, api_token text)"
                )
            result = pii_scan.scan_tables(introspect(conn))

            assert result.status == "FAIL"
            flagged = {(finding.table, finding.column) for finding in result.findings}
            assert ("pii_probe_unclassified", "email") in flagged
            assert ("pii_probe_unclassified", "api_token") in flagged
        finally:
            conn.rollback()


def test_json_output(migrated_scratch_url: str, capsys) -> None:
    assert pii_scan.main(["--url", migrated_scratch_url, "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["table_count"] >= 34
