from __future__ import annotations

import pytest

from scripts import audit_schema


@pytest.fixture(scope="module")
def scratch_url():
    with audit_schema.scratch_database(
        prefix="musawiq_audit_test", quiet=True
    ) as url:
        yield url
