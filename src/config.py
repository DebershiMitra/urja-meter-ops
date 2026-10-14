"""Configuration settings for Urja Meter Ops Modern API."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    # Urja Ops Legacy Portal credentials and URLs
    portal_base_url: str = Field(
        default="https://urja-ops.flockenergy.tech",
        description="Base URL of the upstream Urja Meter Ops legacy portal"
    )
    portal_username: str = Field(
        default="operator@urja.local",
        description="Portal login username / email"
    )
    portal_password: str = Field(
        default="urja-ops-2026",
        description="Portal login password"
    )

    # API Server configuration
    host: str = Field(default="0.0.0.0", description="API host")
    port: int = Field(default=8000, description="API port")
    debug: bool = Field(default=False, description="Debug mode")

    # Cache configuration
    cache_ttl_seconds: int = Field(
        default=3600,
        description="Cache TTL in seconds for bulk meter & hierarchy dataset (default 1 hr)"
    )
    energy_cache_ttl_seconds: int = Field(
        default=300,
        description="Cache TTL in seconds for meter energy timeseries (default 5 mins)"
    )

    # HTTP Client configuration
    client_timeout_seconds: float = Field(
        default=30.0,
        description="Upstream request timeout in seconds"
    )
    client_max_retries: int = Field(
        default=3,
        description="Max retries for upstream requests with exponential backoff"
    )

    model_config = SettingsConfigDict(
        env_prefix="URJA_",
        case_sensitive=False,
    )


settings = Settings()
