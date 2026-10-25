from __future__ import annotations

import json

import psycopg

from scripts import audit_schema, schema_manifest


def test_audit_json_scratch_reports_declared_tables(capsys) -> None:
    result = audit_schema.main(["--scratch", "--json"])
    report = json.loads(capsys.readouterr().out)

    assert report["summary"]["tables"] == len(schema_manifest.TABLES)
    assert report["summary"]["tables"] >= 26
    assert "stores" in report["table_names"]
    assert "audit_logs" in report["table_names"]
    assert len(report["checks"]) == len(audit_schema.CHECKS)
    expected_exit = 1 if report["summary"][audit_schema.FAIL] else 0
    assert result == expected_exit


def test_fk_index_check_detects_unindexed_foreign_key(scratch_url) -> None:
    conn = psycopg.connect(audit_schema.libpq_url(scratch_url))
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE audit_fk_violation_tmp (
                    id uuid PRIMARY KEY DEFAULT uuidv7(),
                    store_id uuid NOT NULL,
                    CONSTRAINT fk_audit_fk_violation_tmp_store_id
                        FOREIGN KEY (store_id) REFERENCES stores (id)
                )
                """
            )

        check = audit_schema.check_fk_indexes(conn)

        assert check.status == audit_schema.FAIL
        assert any(
            detail.startswith("audit_fk_violation_tmp.store_id")
            for detail in check.details
        )
    finally:
        conn.rollback()
        conn.close()

    with psycopg.connect(audit_schema.libpq_url(scratch_url)) as verify:
        with verify.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('public.audit_fk_violation_tmp')"
            )
            assert cur.fetchone()[0] is None
