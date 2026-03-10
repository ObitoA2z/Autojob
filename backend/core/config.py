from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AutoInfluence"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    database_url: str = "postgresql+psycopg2://autoinfluence:autoinfluence@localhost:5432/autoinfluence"
    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    openclaw_enabled: bool = True
    openclaw_base_url: str = "http://localhost:3000"
    playwright_headless: bool = True

    # Optional: comma-separated origins for FastAPI CORS middleware.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Comma-separated list of connector names to enable.
    enabled_platforms: str = "reachr,modash,upfluence,collabstr,aspire"

    collabstr_email: str | None = None
    collabstr_password: str | None = None
    collabstr_login_url: str = "https://collabstr.com/login"
    collabstr_campaigns_url: str = "https://collabstr.com/campaigns"
    collabstr_storage_state_path: str = ".cache/collabstr_state.json"

    scheduler_scan_cron: str = "*/30 * * * *"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
