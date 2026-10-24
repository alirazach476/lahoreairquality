"""Tests for environment-backed configuration loading and validation."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from lahore_air_quality.config import Settings, get_settings, load_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove project-related env vars so defaults and explicit values are isolatable."""
    keys = [
        "OPENAQ_API_KEY",
        "OPENAQ_BASE_URL",
        "OPENMETEO_BASE_URL",
        "OPENMETEO_ARCHIVE_BASE_URL",
        "LAHORE_LATITUDE",
        "LAHORE_LONGITUDE",
        "POLL_INTERVAL_SECONDS",
        "POLL_ONCE",
        "POLL_ENABLE_OPENAQ",
        "POLL_ENABLE_OPENMETEO",
        "LOG_LEVEL",
        "LOG_JSON",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "REDPANDA_BROKERS",
        "REDPANDA_TOPIC",
        "REDPANDA_TOPIC_AIR_QUALITY",
        "REDPANDA_TOPIC_WEATHER",
        "REDPANDA_CONSUMER_GROUP",
        "S3_ENDPOINT_URL",
        "S3_BUCKET",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
        "MLFLOW_TRACKING_URI",
        "API_HOST",
        "API_PORT",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_loads_safe_local_defaults(clean_env: None) -> None:
    settings = Settings(_env_file=None)

    assert settings.openaq_base_url == "https://api.openaq.org"
    assert settings.openmeteo_base_url == "https://api.open-meteo.com"
    assert settings.openmeteo_archive_base_url == "https://archive-api.open-meteo.com"
    assert settings.lahore_latitude == 31.5204
    assert settings.lahore_longitude == 74.3587
    assert settings.poll_interval_seconds == 300.0
    assert settings.poll_once is False
    assert settings.poll_enable_openaq is True
    assert settings.poll_enable_openmeteo is True
    assert settings.log_level == "INFO"
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432
    assert settings.postgres_db == "lahore_aqi"
    assert settings.postgres_user == "lahore"
    assert settings.postgres_password.get_secret_value() == "change_me"
    assert settings.redpanda_brokers == "localhost:19092"
    assert settings.redpanda_topic_air_quality == "aq.raw"
    assert settings.redpanda_topic_weather == "weather.raw"
    assert settings.redpanda_consumer_group == "lahore-aqi-consumer"
    assert settings.s3_endpoint_url == "http://localhost:9000"
    assert settings.s3_bucket == "lahore-aqi-raw"
    assert settings.aws_access_key_id.get_secret_value() == "minioadmin"
    assert settings.aws_secret_access_key.get_secret_value() == "minioadmin"
    assert settings.aws_region == "us-east-1"
    assert settings.mlflow_tracking_uri == "http://localhost:5000"
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8000
    assert settings.openaq_api_key_configured is False


def test_loads_values_from_environment(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAQ_API_KEY", "test-openaq-key")
    monkeypatch.setenv("OPENAQ_BASE_URL", "https://example-openaq.test")
    monkeypatch.setenv("OPENMETEO_BASE_URL", "https://example-meteo.test")
    monkeypatch.setenv("OPENMETEO_ARCHIVE_BASE_URL", "https://example-archive.test")
    monkeypatch.setenv("LAHORE_LATITUDE", "31.55")
    monkeypatch.setenv("LAHORE_LONGITUDE", "74.33")
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_DB", "aqi_prod")
    monkeypatch.setenv("POSTGRES_USER", "aqi_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "s3cret-db")
    monkeypatch.setenv("REDPANDA_BROKERS", "redpanda:9092")
    monkeypatch.setenv("REDPANDA_TOPIC_AIR_QUALITY", "aq.events")
    monkeypatch.setenv("REDPANDA_TOPIC_WEATHER", "wx.events")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_BUCKET", "prod-raw")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA_TEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret-value")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("API_PORT", "9000")

    settings = Settings(_env_file=None)

    assert settings.openaq_api_key.get_secret_value() == "test-openaq-key"
    assert settings.openaq_api_key_configured is True
    assert settings.openaq_base_url == "https://example-openaq.test"
    assert settings.openmeteo_base_url == "https://example-meteo.test"
    assert settings.openmeteo_archive_base_url == "https://example-archive.test"
    assert settings.lahore_latitude == 31.55
    assert settings.lahore_longitude == 74.33
    assert settings.postgres_host == "db.internal"
    assert settings.postgres_port == 6543
    assert settings.postgres_db == "aqi_prod"
    assert settings.postgres_user == "aqi_user"
    assert settings.postgres_password.get_secret_value() == "s3cret-db"
    assert settings.redpanda_brokers == "redpanda:9092"
    assert settings.redpanda_topic_air_quality == "aq.events"
    assert settings.redpanda_topic_weather == "wx.events"
    assert settings.s3_endpoint_url == "http://minio:9000"
    assert settings.s3_bucket == "prod-raw"
    assert settings.aws_access_key_id.get_secret_value() == "AKIA_TEST"
    assert settings.aws_secret_access_key.get_secret_value() == "aws-secret-value"
    assert settings.aws_region == "eu-west-1"
    assert settings.mlflow_tracking_uri == "http://mlflow:5000"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 9000


def test_loads_from_env_file(clean_env: None, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPENAQ_API_KEY=file-key",
                "POSTGRES_HOST=from-file",
                "POSTGRES_PASSWORD=file-password",
                "REDPANDA_TOPIC_AIR_QUALITY=file.aq",
                "REDPANDA_TOPIC_WEATHER=file.wx",
                "API_PORT=8111",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings(env_file=str(env_path))

    assert settings.openaq_api_key.get_secret_value() == "file-key"
    assert settings.postgres_host == "from-file"
    assert settings.postgres_password.get_secret_value() == "file-password"
    assert settings.redpanda_topic_air_quality == "file.aq"
    assert settings.redpanda_topic_weather == "file.wx"
    assert settings.api_port == 8111


def test_rejects_invalid_port(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PORT", "70000")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "api_port" in str(exc_info.value)


def test_rejects_blank_postgres_host(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "   ")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "postgres_host" in str(exc_info.value)


def test_rejects_invalid_base_url(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAQ_BASE_URL", "not-a-url")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "openaq_base_url" in str(exc_info.value)


def test_rejects_blank_required_secret(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "   ")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "postgres_password" in str(exc_info.value)


def test_strips_trailing_slash_from_base_urls(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAQ_BASE_URL", "https://api.openaq.org/")
    monkeypatch.setenv("OPENMETEO_BASE_URL", "https://api.open-meteo.com/")
    settings = Settings(_env_file=None)
    assert settings.openaq_base_url == "https://api.openaq.org"
    assert settings.openmeteo_base_url == "https://api.open-meteo.com"


def test_secrets_are_not_exposed_in_repr_or_redacted_dict(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_password = "super-secret-password-xyz"
    secret_aws = "super-secret-aws-xyz"
    secret_openaq = "super-secret-openaq-xyz"
    monkeypatch.setenv("POSTGRES_PASSWORD", secret_password)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAVISIBLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", secret_aws)
    monkeypatch.setenv("OPENAQ_API_KEY", secret_openaq)

    settings = Settings(_env_file=None)
    rendered = repr(settings)
    as_string = str(settings)
    redacted = settings.redacted_dict()

    for leak in (secret_password, secret_aws, secret_openaq, "AKIAVISIBLE"):
        assert leak not in rendered
        assert leak not in as_string
        assert leak not in str(redacted)

    assert redacted["postgres_password"] == "***REDACTED***"
    assert redacted["aws_access_key_id"] == "***REDACTED***"
    assert redacted["aws_secret_access_key"] == "***REDACTED***"
    assert redacted["openaq_api_key"] == "***REDACTED***"


def test_get_settings_is_cached(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PORT", "8001")
    first = get_settings()
    monkeypatch.setenv("API_PORT", "8002")
    second = get_settings()
    assert first is second
    assert second.api_port == 8001

    get_settings.cache_clear()
    third = get_settings()
    assert third.api_port == 8002


def test_postgres_dsn_uses_secret_but_is_not_in_repr(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "dsn-secret-value")
    settings = Settings(_env_file=None)
    dsn = settings.postgres_dsn
    assert "dsn-secret-value" in dsn
    assert "dsn-secret-value" not in repr(settings)
