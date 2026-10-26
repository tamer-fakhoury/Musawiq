"""Route wiring smoke test.

Tests that build a local FastAPI instance hide wiring gaps: a router can be
fully tested and still be absent from ``create_app``. This test reads the real
application's OpenAPI schema and fails if a router is not wired in.
"""

from __future__ import annotations

from musawiq.api.app import create_app


def test_real_app_registers_every_router():
    paths = create_app().openapi()["paths"]

    expected = {
        "/health",
        "/audit-logs",
        "/audit-logs/export.csv",
        "/jobs/{job_type}",
        "/jobs/{job_id}",
        "/jobs/{job_id}/retry",
        "/ai/status",
        "/ai/generate",
        "/imports",
        "/imports/template.csv",
        "/imports/{batch_id}",
        "/imports/{batch_id}/validate",
        "/imports/{batch_id}/preview",
        "/imports/{batch_id}/error-report.csv",
        "/categories",
        "/niches",
        "/audience-profiles",
        "/audience-profiles/current",
        "/audience-profiles/{profile_id}/segments",
        "/campaigns",
        "/campaigns/{campaign_id}",
        "/campaigns/{campaign_id}/adsets",
        "/campaigns/{campaign_id}/variations",
        "/campaigns/{campaign_id}/signals",
        "/ad-variations/{variation_id}",
    }

    missing = expected - set(paths)
    assert missing == set(), f"routers not wired into create_app: {sorted(missing)}"
