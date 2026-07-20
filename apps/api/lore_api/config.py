from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LORE_", extra="ignore")

    database_url: str = "postgresql+asyncpg://lore:lore_dev_password@localhost:5433/lore"
    jwt_secret: str = "dev-only-change-me"
    access_token_ttl_seconds: int = 60 * 15
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30
    cors_origins: list[str] = ["http://localhost:3000"]
    upload_dir: str = "uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()
