"""Tests for the schema documentation generator."""

from __future__ import annotations

from scripts import gen_schema_docs


def test_scratch_generates_schema_document() -> None:
    result = gen_schema_docs.main(["--scratch"])

    assert result == 0
    assert gen_schema_docs.DEFAULT_OUTPUT.is_file()
    document = gen_schema_docs.DEFAULT_OUTPUT.read_text(encoding="utf-8")
    assert "## `stores`" in document
    assert "## `audit_logs`" in document
    assert "| `stores` | `Store` | mapped |" in document
    assert "| `audit_logs` | `AuditLog` | mapped |" in document
