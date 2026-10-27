from functools import lru_cache

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIOFETCH_", env_file=".env", extra="forbid", frozen=True
    )

    base_url: HttpUrl
    api_key: SecretStr
    max_concurrency: int = Field(default=20, gt=0)
    attempts: int = Field(default=4, gt=0)
    timeout: float = Field(default=10.0, gt=0)
    requests_per_minute: int | None = Field(default=None, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # the environment fills the fields
