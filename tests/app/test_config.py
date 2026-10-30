"""Configuration contract."""

from __future__ import annotations

import pytest

from musawiq.config import ConfigurationError, get_settings


def test_missing_database_url_fails_fast(monkeypatch) -> None:
    monkeypatch.setenv("MUSAWIQ_DATABASE_URL", "")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="MUSAWIQ_DATABASE_URL"):
        get_settings()

def test_dev_tenant_fallback_requires_explicit_development_opt_in(monkeypatch) -> None:
    from musawiq.api.app import create_app
    from musawiq.db.session import dispose_engine
    from musawiq.middleware.tenant import DevHeaderTenantProvider

    monkeypatch.setenv(
        "MUSAWIQ_DATABASE_URL",
        "postgresql+psycopg://user:pass@127.0.0.1:1/test",
    )
    monkeypatch.setenv("MUSAWIQ_APP_ENV", "development")
    monkeypatch.setenv("MUSAWIQ_ALLOW_DEV_TENANT_FALLBACK", "false")
    monkeypatch.setenv("MUSAWIQ_DEV_STORE_ID", "22222222-2222-4222-8222-000000000002")
    monkeypatch.setenv("MUSAWIQ_DEV_USER_ID", "11111111-1111-4111-8111-000000000001")
    get_settings.cache_clear()
    try:
        app = create_app()
        assert isinstance(app.state.tenant_provider, DevHeaderTenantProvider)
        assert app.state.tenant_provider.default_store_id is None
    finally:
        dispose_engine()
        get_settings.cache_clear()


def test_dev_tenant_fallback_is_rejected_outside_development(monkeypatch) -> None:
    from musawiq.api.app import create_app
    from musawiq.db.session import dispose_engine

    monkeypatch.setenv(
        "MUSAWIQ_DATABASE_URL",
        "postgresql+psycopg://user:pass@127.0.0.1:1/test",
    )
    monkeypatch.setenv("MUSAWIQ_APP_ENV", "production")
    monkeypatch.setenv("MUSAWIQ_ALLOW_DEV_TENANT_FALLBACK", "true")
    get_settings.cache_clear()
    try:
        with pytest.raises(
            ConfigurationError, match="MUSAWIQ_ALLOW_DEV_TENANT_FALLBACK"
        ):
            create_app()
    finally:
        dispose_engine()
        get_settings.cache_clear()
