"""AI analysis migration, schema, and evidence validation."""

from __future__ import annotations

from copy import deepcopy

import psycopg
import pytest

from musawiq.ai.analysis.service import (
    AnalysisValidationError,
    validate_result,
)
from scripts.gen_schema_docs import libpq_url

VALID = {
    "demand": {
        "level": "weak",
        "confidence": 0.8,
        "rationale_ar": "الإشارات ضعيفة لكنها كافية لبدء التحسين.",
    },
    "issues": [
        {
            "type": "content",
            "severity": "high",
            "metric": "ctr",
            "observed": 0.012,
            "benchmark": 0.02,
            "rationale_ar": "نص الإعلان لا يوضح الفائدة.",
        }
    ],
    "recommendations": [
        {
            "action": "change_copy",
            "target": "ad_1",
            "change_ar": "أعد كتابة العنوان.",
            "expected_impact_ar": "تحسين معدل النقر.",
            "confidence": 0.7,
            "copy_paste_ar": "اكتشف الفرق اليوم.",
        }
    ],
    "next_steps_ar": ["جرّب نصاً جديداً لمدة أسبوع."],
}
METRICS = {"ctr": 0.012, "spend": 100, "clicks": 40}


def test_migration_creates_table_and_indexes(migrated_url) -> None:
    with psycopg.connect(libpq_url(migrated_url)) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.ai_analyses')")
            assert cur.fetchone()[0] == "ai_analyses"

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'ai_analyses'
                """
            )
            columns = {row[0] for row in cur.fetchall()}
            assert {
                "id",
                "store_id",
                "campaign_id",
                "parent_analysis_id",
                "input_snapshot",
                "result",
                "demand_level",
                "confidence",
                "created_by",
            } <= columns

            cur.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'ai_analyses'
                """
            )
            indexes = {row[0] for row in cur.fetchall()}
            assert {
                "ix_ai_analyses_campaign_id_created_at",
                "ix_ai_analyses_parent_analysis_id",
            } <= indexes


def test_valid_payload_passes() -> None:
    result = validate_result(deepcopy(VALID), METRICS)

    assert result.demand.level == "weak"
    assert result.demand.confidence == 0.8
    assert result.issues[0].metric == "ctr"
    assert result.recommendations[0].action == "change_copy"


def test_missing_field_is_rejected() -> None:
    payload = deepcopy(VALID)
    payload.pop("next_steps_ar")

    with pytest.raises(AnalysisValidationError):
        validate_result(payload, METRICS)


def test_unknown_enum_is_rejected() -> None:
    payload = deepcopy(VALID)
    payload["demand"]["level"] = "excellent"

    with pytest.raises(AnalysisValidationError):
        validate_result(payload, METRICS)


def test_fabricated_observed_value_is_rejected() -> None:
    payload = deepcopy(VALID)
    payload["issues"][0]["observed"] = 0.5

    with pytest.raises(AnalysisValidationError):
        validate_result(payload, METRICS)
