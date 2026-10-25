"""Configuration contract."""

from __future__ import annotations

import pytest

from musawiq.config import ConfigurationError, get_settings


def test_missing_database_url_fails_fast(monkeypatch) -> None:
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", "")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="MUSAWIQ_DATABASE_URL"):
        get_settings()
