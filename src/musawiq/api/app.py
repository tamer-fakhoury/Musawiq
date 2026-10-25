"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from musawiq import __version__
from musawiq.api.routers.health import router as health_router
from musawiq.config import get_settings
from musawiq.db.session import dispose_engine, get_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    get_engine()
    try:
        yield
    finally:
        dispose_engine()


def create_app() -> FastAPI:
    """Build the application.

    Configuration is loaded here, not at import time, so importing this module
    never requires a database URL. Creating the app fails fast when the URL is
    missing.
    """
    settings = get_settings()
    app = FastAPI(
        title="Musawiq API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(health_router)
    return app
