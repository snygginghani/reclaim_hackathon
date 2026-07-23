from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LORE_", extra="ignore")

    database_url: str = "postgresql+asyncpg://lore:lore_dev_password@localhost:5433/lore"
    jwt_secret: str = "dev-only-change-me"
    access_token_ttl_seconds: int = 60 * 15
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30
    cors_origins: list[str] = ["http://localhost:3000"]
    # Matches the web app on any private-LAN address (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
    # on port 3000, so a dev instance is reachable from other machines on the same network
    # without hardcoding any one IP.
    cors_origin_regex: str = (
        r"^http://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}):3000$"
    )
    upload_dir: str = "uploads"

    # Public base URL of this API, used to build absolute URLs for uploaded assets
    # (imported Notion images live under {api_base_url}/uploads/...).
    api_base_url: str = "http://localhost:8300"

    # Notion OAuth ("Connect Notion" migration). Registered once by the team at
    # notion.so/my-integrations; when unset, the Connect button reports "not
    # configured" instead of failing. The redirect URI must match the integration.
    notion_client_id: str | None = None
    notion_client_secret: str | None = None
    notion_redirect_uri: str = "http://localhost:8300/api/notion/oauth/callback"
    # Web origin to bounce back to after the OAuth callback completes.
    web_base_url: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
