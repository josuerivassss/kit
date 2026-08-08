"""Centralized, validated application configuration.

All environment-derived settings are declared here and validated once at
startup via pydantic. This replaces scattered `os.getenv()` calls with a
single, typed, fail-fast source of truth.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Discord
    token: str = Field(alias="TOKEN")
    owner_ids: str = Field(default="", alias="OWNER_IDS")

    # Sharding
    shard_count: int = Field(default=0, alias="SHARD_COUNT")
    shard_ids: str = Field(default="", alias="SHARD_IDS")
    cluster_id: int = Field(default=0, alias="CLUSTER_ID")

    # MongoDB
    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    mongo_db_name: str = Field(default="bcommie", alias="MONGO_DB_NAME")

    # PostgreSQL
    postgres_dsn: str = Field(alias="POSTGRES_DSN")
    postgres_pool_min: int = Field(default=2, alias="POSTGRES_POOL_MIN")
    postgres_pool_max: int = Field(default=10, alias="POSTGRES_POOL_MAX")

    # Observability
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")

    # Security
    command_rate_limit_per_minute: int = Field(default=20, alias="COMMAND_RATE_LIMIT_PER_MINUTE")

    # Dashboard (extensibility)
    dashboard_enabled: bool = Field(default=False, alias="DASHBOARD_ENABLED")
    dashboard_host: str = Field(default="0.0.0.0", alias="DASHBOARD_HOST")
    dashboard_port: int = Field(default=8080, alias="DASHBOARD_PORT")
    dashboard_jwt_secret: str = Field(default="change-me", alias="DASHBOARD_JWT_SECRET")

    # Service Commie
    api_base_url: str = Field(default="http://localhost:3000", alias="API_BASE_URL")
    api_admin_secret: str = Field(default="", alias="API_ADMIN_SECRET")

    # --- Error reporting ---------------------------------------------------
    error_webhook_url: str = Field(default="", alias="ERROR_WEBHOOK_URL")

    @field_validator("log_format")
    @classmethod
    def _validate_log_format(cls, value: str) -> str:
        if value not in {"json", "console"}:
            raise ValueError("LOG_FORMAT must be 'json' or 'console'")
        return value

    @property
    def owner_id_list(self) -> list[int]:
        """Parsed list of bot owner Discord IDs."""
        return [int(x) for x in self.owner_ids.split(",") if x.strip()]

    @property
    def shard_id_list(self) -> list[int] | None:
        """Explicit shard IDs for this process, or None to let discord.py decide."""
        if not self.shard_ids.strip():
            return None
        return [int(x) for x in self.shard_ids.split(",") if x.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached, validated Settings instance (loaded once per process)."""
    return Settings()  # type: ignore[call-arg]
