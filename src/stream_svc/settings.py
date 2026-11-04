from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STREAM_", env_file=".env", extra="ignore"
    )
    upstream_url: str = "http://localhost:9000"
    fake_upstream: bool = False
    upstream_timeout: float = Field(default=10.0, gt=0)
    upstream_attempts: int = Field(default=3, ge=1)
    cors_origins: list[str] = []
    heartbeat_seconds: float = Field(default=15.0, gt=0)
    retry_after_seconds: int = Field(default=5, ge=1)
    api_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@lru_cache
def get_settings():
    return Settings()
