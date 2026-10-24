"""Application settings resource — credentials never hard-coded."""

from __future__ import annotations

from dagster import ConfigurableResource

from lahore_air_quality.config import Settings, get_settings, load_settings


class AppSettingsResource(ConfigurableResource):
    """Loads ``lahore_air_quality.config.Settings`` from the environment / ``.env``."""

    env_file: str | None = None

    def get_settings(self) -> Settings:
        get_settings.cache_clear()
        if self.env_file:
            return load_settings(env_file=self.env_file)
        return get_settings()
