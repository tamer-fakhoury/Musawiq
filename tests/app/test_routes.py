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
    }

    missing = expected - set(paths)
    assert missing == set(), f"routers not wired into create_app: {sorted(missing)}"
