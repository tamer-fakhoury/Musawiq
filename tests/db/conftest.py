from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine


@pytest.fixture(scope="session")
def db_url() -> str:
    url = os.getenv("MUSAWIQ_TEST_DATABASE_URL")
    if not url:
        pytest.fail("MUSAWIQ_TEST_DATABASE_URL is not set; run scripts.verify_db")
    return url


@pytest.fixture(scope="session")
def engine(db_url):
    eng = create_engine(db_url, future=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def conn(engine):
    with engine.connect() as connection:
        yield connection
        connection.rollback()
