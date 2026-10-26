"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from musawiq import __version__
from musawiq.api.routers.ai import router as ai_router
from musawiq.api.routers.audit import router as audit_router
from musawiq.api.routers.campaigns import router as campaigns_router
from musawiq.api.routers.audiences import router as audiences_router
from musawiq.api.routers.categories import router as categories_router
from musawiq.api.routers.health import router as health_router
from musawiq.api.routers.import_preview import router as import_preview_router
from musawiq.api.routers.imports import router as imports_router
from musawiq.api.routers.jobs import router as jobs_router
from musawiq.config import ConfigurationError, get_settings
from musawiq.db.session import dispose_engine, get_engine
from musawiq.middleware.tenant import (
    DevHeaderTenantProvider,
    TenantMiddleware,
    TenantProvider,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    get_engine()
    try:
        yield
    finally:
        dispose_engine()


def create_app(tenant_provider: TenantProvider | None = None) -> FastAPI:
    """Build the application.

    Configuration is loaded here, not at import time, so importing this module
    never requires a database URL. Creating the app fails fast when the URL is
    missing.

    ``tenant_provider`` exists so P1-A3 can replace the temporary header-based
    development provider without changing the middleware or dependencies.
    """
    settings = get_settings()
    provider = tenant_provider or DevHeaderTenantProvider()

    if settings.app_env == "production" and isinstance(
        provider, DevHeaderTenantProvider
    ):
        raise ConfigurationError(
            "The development header tenant provider is disabled in production. "
            "Configure real authentication before running with MUSAWIQ_APP_ENV=production."
        )

    app = FastAPI(
        title="Musawiq API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.tenant_provider = provider
    app.add_middleware(TenantMiddleware, provider=provider)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )
    app.include_router(health_router)
    app.include_router(audit_router)
    app.include_router(jobs_router)
    app.include_router(ai_router)
    app.include_router(imports_router)
    app.include_router(import_preview_router)
    app.include_router(audiences_router)
    app.include_router(categories_router)
    app.include_router(campaigns_router)
    return app

