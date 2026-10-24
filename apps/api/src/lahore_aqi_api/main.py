"""FastAPI application factory and CLI entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lahore_air_quality.db.session import dispose_engine
from lahore_aqi_api import __version__
from lahore_aqi_api.api.router import api_router
from lahore_aqi_api.core.config import get_api_settings, get_platform_settings
from lahore_aqi_api.core.errors import register_exception_handlers
from lahore_aqi_api.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("api_startup version=%s", __version__)
    yield
    dispose_engine()
    logger.info("api_shutdown")


def create_app(*, for_testing: bool = False) -> FastAPI:
    """Build the FastAPI application (CORS, routes, OpenAPI, error handlers)."""
    api_settings = get_api_settings()
    platform = get_platform_settings()
    if not for_testing:
        configure_logging(level=platform.log_level, json_logs=platform.log_json)

    app = FastAPI(
        title=api_settings.api_title,
        version=api_settings.api_version,
        description=(
            "Lahore Air Quality Intelligence Platform API. "
            "Serves current/historical AQI, forecasts, sensors, and data-quality "
            "summaries. Database credentials are never exposed in responses."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_origins_list,
        allow_credentials=api_settings.api_cors_allow_credentials,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, Any]:
        return {
            "service": "lahore-aqi-api",
            "version": api_settings.api_version,
            "docs": "/docs",
        }

    return app


app = create_app()


def run() -> None:
    """CLI: ``lahore-aqi-api`` / ``python -m lahore_aqi_api.main``."""
    platform = get_platform_settings()
    configure_logging(level=platform.log_level, json_logs=platform.log_json)
    # Host/port from env-based platform settings — never log DSN/password.
    logger.info(
        "api_listen host=%s port=%s",
        platform.api_host,
        platform.api_port,
    )
    uvicorn.run(
        "lahore_aqi_api.main:app",
        host=platform.api_host,
        port=platform.api_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
