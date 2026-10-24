"""Central application configuration loaded from environment variables.

Secrets are never included in ``repr`` / ``str`` output. Callers that need a
secret value must read it explicitly (e.g. ``settings.postgres_password.get_secret_value()``).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Final
from urllib.parse import quote_plus, urlparse

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Field names whose values must never appear in logs or repr output.
_SECRET_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "openaq_api_key",
        "postgres_password",
        "aws_access_key_id",
        "aws_secret_access_key",
    }
)

_REDACTED: Final[str] = "***REDACTED***"


def _is_blank(value: str | None) -> bool:
    return value is None or value.strip() == ""


def _require_non_blank(value: str, field_name: str) -> str:
    if _is_blank(value):
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)
    return value.strip()


def _validate_http_base_url(value: str, field_name: str) -> str:
    cleaned = _require_non_blank(value, field_name)
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        msg = f"{field_name} must be an absolute http(s) URL with a host"
        raise ValueError(msg)
    return cleaned.rstrip("/")


def _validate_port(value: int, field_name: str) -> int:
    if not 1 <= value <= 65535:
        msg = f"{field_name} must be between 1 and 65535 inclusive"
        raise ValueError(msg)
    return value


class Settings(BaseSettings):
    """Typed settings for all platform components.

    Values are loaded from process environment variables and, if present, a
    local ``.env`` file. No credentials are hard-coded for production use;
    defaults exist only to make local Docker Compose development workable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    # --- External APIs ---
    openaq_api_key: SecretStr = Field(
        default_factory=lambda: SecretStr(""),
        description="OpenAQ API key (optional until ingestion requires it).",
    )
    openaq_base_url: str = Field(
        default="https://api.openaq.org",
        description="OpenAQ API base URL (no trailing slash).",
    )
    openmeteo_base_url: str = Field(
        default="https://api.open-meteo.com",
        description="Open-Meteo forecast/current API base URL (no trailing slash).",
    )
    openmeteo_archive_base_url: str = Field(
        default="https://archive-api.open-meteo.com",
        description="Open-Meteo Historical Weather API base URL (no trailing slash).",
    )

    # --- Geography (Lahore) — single configurable source for clients ---
    lahore_latitude: float = Field(
        default=31.5204,
        description="WGS84 latitude used for Lahore weather/AQ targeting.",
    )
    lahore_longitude: float = Field(
        default=74.3587,
        description="WGS84 longitude used for Lahore weather/AQ targeting.",
    )

    # --- PostgreSQL ---
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="lahore_aqi")
    postgres_user: str = Field(default="lahore")
    postgres_password: SecretStr = Field(
        default_factory=lambda: SecretStr("change_me"),
        description="Local-only default; change before shared environments.",
    )

    # --- Redpanda (Kafka-compatible) ---
    redpanda_brokers: str = Field(
        default="localhost:19092",
        description="Comma-separated Kafka bootstrap brokers (Redpanda).",
    )
    redpanda_topic_air_quality: str = Field(
        default="aq.raw",
        description="Topic for air-quality ingestion events.",
    )
    redpanda_topic_weather: str = Field(
        default="weather.raw",
        description="Topic for weather ingestion events.",
    )
    redpanda_consumer_group: str = Field(
        default="lahore-aqi-consumer",
        description="Kafka consumer group id for the ingestion consumer.",
    )

    # --- S3 / MinIO ---
    s3_endpoint_url: str = Field(default="http://localhost:9000")
    s3_bucket: str = Field(default="lahore-aqi-raw")
    aws_access_key_id: SecretStr = Field(
        default_factory=lambda: SecretStr("minioadmin"),
        description="Local MinIO default; supply real credentials outside local Compose.",
    )
    aws_secret_access_key: SecretStr = Field(
        default_factory=lambda: SecretStr("minioadmin"),
        description="Local MinIO default; supply real credentials outside local Compose.",
    )
    aws_region: str = Field(default="us-east-1")

    # --- MLflow ---
    mlflow_tracking_uri: str = Field(default="http://localhost:5000")

    # --- Poller ---
    poll_interval_seconds: float = Field(
        default=300.0,
        description="Seconds between poll cycles for air-quality and weather.",
    )
    poll_once: bool = Field(
        default=False,
        description="When true, run a single poll cycle then exit (useful for tests/cron).",
    )
    poll_enable_openaq: bool = Field(
        default=True,
        description="Fetch OpenAQ air-quality data during each poll cycle.",
    )
    poll_enable_openmeteo: bool = Field(
        default=True,
        description="Fetch Open-Meteo weather data during each poll cycle.",
    )
    log_level: str = Field(default="INFO", description="Root log level for services.")
    log_json: bool = Field(
        default=True,
        description="Emit one JSON object per log line when true.",
    )

    # --- API ---
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    @field_validator(
        "openaq_base_url",
        "openmeteo_base_url",
        "openmeteo_archive_base_url",
        "s3_endpoint_url",
        "mlflow_tracking_uri",
    )
    @classmethod
    def validate_base_urls(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "url"
        return _validate_http_base_url(value, field_name)

    @field_validator("lahore_latitude")
    @classmethod
    def validate_lahore_latitude(cls, value: float) -> float:
        if not -90.0 <= value <= 90.0:
            msg = "lahore_latitude must be between -90 and 90"
            raise ValueError(msg)
        return value

    @field_validator("lahore_longitude")
    @classmethod
    def validate_lahore_longitude(cls, value: float) -> float:
        if not -180.0 <= value <= 180.0:
            msg = "lahore_longitude must be between -180 and 180"
            raise ValueError(msg)
        return value

    @field_validator("postgres_host", "postgres_db", "postgres_user")
    @classmethod
    def validate_non_blank_postgres(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "postgres_field"
        return _require_non_blank(value, field_name)

    @field_validator(
        "redpanda_brokers",
        "redpanda_topic_air_quality",
        "redpanda_topic_weather",
        "redpanda_consumer_group",
        "s3_bucket",
        "aws_region",
        "api_host",
    )
    @classmethod
    def validate_non_blank_infra(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name or "field"
        return _require_non_blank(value, field_name)

    @field_validator("postgres_port", "api_port")
    @classmethod
    def validate_ports(cls, value: int, info: ValidationInfo) -> int:
        field_name = info.field_name or "port"
        return _validate_port(value, field_name)

    @field_validator("poll_interval_seconds")
    @classmethod
    def validate_poll_interval(cls, value: float) -> float:
        if value <= 0:
            msg = "poll_interval_seconds must be > 0"
            raise ValueError(msg)
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        cleaned = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if cleaned not in allowed:
            msg = f"log_level must be one of {sorted(allowed)}"
            raise ValueError(msg)
        return cleaned

    @field_validator("postgres_password", "aws_access_key_id", "aws_secret_access_key")
    @classmethod
    def validate_required_secrets(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        field_name = info.field_name or "secret"
        if _is_blank(value.get_secret_value()):
            msg = f"{field_name} must not be empty"
            raise ValueError(msg)
        return value

    @property
    def openaq_api_key_configured(self) -> bool:
        """Return True when an OpenAQ API key has been supplied."""
        return not _is_blank(self.openaq_api_key.get_secret_value())

    @property
    def postgres_dsn(self) -> str:
        """SQLAlchemy-style Postgres DSN with the password embedded.

        Prefer this only at connection time. Do not log the return value.
        """
        password = quote_plus(self.postgres_password.get_secret_value())
        user = quote_plus(self.postgres_user)
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def redacted_dict(self) -> dict[str, Any]:
        """Return settings as a dict with secret fields replaced by a placeholder."""
        data: dict[str, Any] = {}
        for name in type(self).model_fields:
            value = getattr(self, name)
            if name in _SECRET_FIELD_NAMES or isinstance(value, SecretStr):
                data[name] = _REDACTED
            else:
                data[name] = value
        return data

    def __repr__(self) -> str:
        parts = [f"{key}={value!r}" for key, value in self.redacted_dict().items()]
        return f"Settings({', '.join(parts)})"

    def __str__(self) -> str:
        return repr(self)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache settings from the environment.

    Call ``get_settings.cache_clear()`` in tests after mutating environment
    variables so subsequent calls re-read configuration.
    """
    return Settings()


def load_settings(*, env_file: str | None = None) -> Settings:
    """Load settings without using the process-wide cache.

    Args:
        env_file: Optional path to a dotenv file. When ``None``, uses the
            default ``.env`` discovery from :class:`Settings`.
    """
    if env_file is None:
        return Settings()
    return Settings(_env_file=env_file)
