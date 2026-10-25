"""Tests for the schema documentation generator."""

from __future__ import annotations

from pathlib import Path

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


def test_check_passes_when_document_is_in_sync(capsys) -> None:
    before = gen_schema_docs.DEFAULT_OUTPUT.read_bytes()

    result = gen_schema_docs.main(["--check"])

    assert result == 0
    assert gen_schema_docs.DEFAULT_OUTPUT.read_bytes() == before
    assert "SCHEMA OK" in capsys.readouterr().out


def test_check_fails_on_a_stale_copy(tmp_path: Path, capsys) -> None:
    original = gen_schema_docs.DEFAULT_OUTPUT.read_text(encoding="utf-8")
    stale_text = original.replace(
        "- Application tables:", "- Stale application tables:", 1
    )
    assert stale_text != original

    stale_path = tmp_path / "SCHEMA.md"
    stale_path.write_text(stale_text, encoding="utf-8", newline="\n")

    result = gen_schema_docs.main(["--check", "--output", str(stale_path)])

    assert result == 1
    assert stale_path.read_text(encoding="utf-8") == stale_text
    captured = capsys.readouterr()
    assert "SCHEMA DRIFT" in captured.err
    assert "## Summary" in captured.err
