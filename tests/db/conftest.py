"""Database test fixtures.

General schema tests use a privileged connection so RLS does not interfere with
constraint-focused tests. The dedicated RLS tests use ``app_conn``, which
connects as ``MUSAWIQ_TEST_DATABASE_URL`` (the non-superuser application role)
and is therefore subject to FORCE ROW LEVEL SECURITY.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import create_engine


def _with_admin_credentials(test_url: str, admin_url: str) -> str:
    test_parts = urlsplit(test_url)
    admin_parts = urlsplit(admin_url)
    return urlunsplit(admin_parts._replace(path=test_parts.path))


@pytest.fixture(scope="session")
def db_url() -> str:
    url = os.getenv("MUSAWIQ_TEST_DATABASE_URL")
    if not url:
        pytest.fail("MUSAWIQ_TEST_DATABASE_URL is not set; run scripts.verify_db")
    return url


@pytest.fixture(scope="session")
def admin_db_url(db_url) -> str:
    admin_url = os.getenv("MUSAWIQ_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.fail(
            "MUSAWIQ_ADMIN_DATABASE_URL is not set; "
            "the DB suite needs a privileged connection under RLS"
        )
    return _with_admin_credentials(db_url, admin_url)


@pytest.fixture(scope="session")
def engine(admin_db_url):
    eng = create_engine(admin_db_url, future=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def conn(engine):
    with engine.connect() as connection:
        yield connection
        connection.rollback()


@pytest.fixture(scope="session")
def app_engine(db_url):
    eng = create_engine(db_url, future=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def app_conn(app_engine):
    with app_engine.connect() as connection:
        yield connection
        connection.rollback()
