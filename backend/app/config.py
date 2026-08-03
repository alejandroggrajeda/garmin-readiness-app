"""Environment-driven settings (12-factor). See `.env.example` for the full
list of required variables and Neon direct-endpoint notes."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://user:pass@localhost:5432/garmin_readiness"
    api_key: str = "dev-local-only-change-me"
    garmin_secret_key: str = ""
    garmin_email: str = ""
    garmin_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
