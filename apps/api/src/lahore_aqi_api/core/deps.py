"""FastAPI dependencies: settings and repository (DB session scoped to repo)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from lahore_air_quality.db.session import get_session_factory
from lahore_aqi_api.core.config import ApiSettings, get_api_settings
from lahore_aqi_api.db.repository import AirQualityRepository, PostgresAirQualityRepository


def get_api_config() -> ApiSettings:
    return get_api_settings()


def get_repository(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_config)],
) -> Iterator[AirQualityRepository]:
    """Yield a repository.

    Tests may set ``app.state.repository`` to a fake implementation so no
    database connection is opened.
    """
    override = getattr(request.app.state, "repository", None)
    if override is not None:
        yield override
        return

    session = get_session_factory()()
    try:
        yield PostgresAirQualityRepository(session, settings=settings)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


ApiConfigDep = Annotated[ApiSettings, Depends(get_api_config)]
RepoDep = Annotated[AirQualityRepository, Depends(get_repository)]
