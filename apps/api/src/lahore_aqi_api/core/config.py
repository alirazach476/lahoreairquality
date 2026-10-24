"""API configuration from environment variables (no secrets in responses)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from lahore_air_quality.config import Settings, get_settings


class ApiSettings(BaseSettings):
    """HTTP-facing settings for the FastAPI service.

    Database credentials come from :class:`~lahore_air_quality.config.Settings`
    and are never returned by API handlers.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    api_title: str = Field(default="Lahore AQI API")
    api_version: str = Field(default="0.1.0")
    # Comma-separated; defaults target local Vite/CRA React apps.
    api_cors_origins: str = Field(
        default=(
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:3000,http://127.0.0.1:3000"
        ),
        description="Comma-separated CORS origins for local React and others.",
    )
    api_cors_allow_credentials: bool = Field(default=True)
    data_freshness_max_seconds: int = Field(
        default=7200,
        description="Observations older than this are marked not fresh.",
    )
    history_default_hours: int = Field(default=24, ge=1)
    history_max_hours: int = Field(default=168, ge=1)
    forecast_artifact_dir: str = Field(
        default="ml/training/artifacts/xgboost",
        description="Directory used when serving forecast metadata from artifacts.",
    )

    @field_validator("data_freshness_max_seconds")
    @classmethod
    def _positive_freshness(cls, value: int) -> int:
        if value < 60:
            raise ValueError("data_freshness_max_seconds must be >= 60")
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [part.strip() for part in self.api_cors_origins.split(",") if part.strip()]


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    return ApiSettings()


def get_platform_settings() -> Settings:
    """Platform settings (DB DSN, host/port). Secrets stay internal."""
    return get_settings()
