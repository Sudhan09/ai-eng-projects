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


@lru_cache
def get_settings():
    return Settings()
