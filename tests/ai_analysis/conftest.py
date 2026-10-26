"""Migrated scratch database for the AI analysis migration test."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from scripts.seed_dev import scratch_database


@pytest.fixture(scope="session")
def migrated_url() -> Iterator[str]:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.skip("MUSAWIQ_ADMIN_DATABASE_URL is not set")
    with scratch_database(admin_url) as url:
        yield url
