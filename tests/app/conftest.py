"""Shared fixtures for the application scaffold tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from musawiq.api.app import create_app
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_DUMMY_DATABASE_URL = "postgresql+psycopg://test:test@127.0.0.1:1/musawiq"


@pytest.fixture(autouse=True)
def reset_app_caches() -> Iterator[None]:
    get_settings.cache_clear()
    dispose_engine()
    yield
    get_settings.cache_clear()
    dispose_engine()


@pytest.fixture()
def app(monkeypatch):
    test_url = os.getenv("MUSAWIQ_TEST_DATABASE_URL")
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", test_url or _DUMMY_DATABASE_URL)
    get_settings.cache_clear()
    dispose_engine()
    return create_app()


@pytest.fixture()
def db_session() -> Iterator[Session]:
    url = os.getenv("MUSAWIQ_TEST_DATABASE_URL")
    if not url:
        pytest.skip("MUSAWIQ_TEST_DATABASE_URL is not set")

    engine = create_engine(url, pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
