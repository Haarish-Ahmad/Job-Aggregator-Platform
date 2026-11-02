"""Runtime configuration, read from environment variables (and an optional backend/.env).

Outside APP_ENV=dev the app refuses to start without a real SECRET_KEY and DATABASE_URL, so a forgotten
variable fails loudly instead of running with a publicly known session key.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-secret-change-me"
DEV_DATABASE_URL = "postgresql://jobs:jobs@localhost:5432/jobs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "dev" relaxes the checks below; anything else is treated as production.
    app_env: str = "production"
    database_url: str = ""
    secret_key: str = ""
    # Comma separated browser origins allowed to call the API with cookies.
    cors_origins: str = "http://localhost:5173,http://localhost"
    # Set when the API is served under a path prefix (nginx strips "/api" and passes it here for /docs).
    root_path: str = ""
    session_cookie_secure: bool = False

    # Scraper -> backend ingest. Empty disables token auth (admin cookie sessions still work).
    ingest_token: str = ""
    # Admin bootstrap (python cli.py bootstrap-admin). Both must be set to do anything.
    admin_email: str = ""
    admin_password: str = ""

    # Email alerts. Mailpit in dev (smtp_host=mailpit, 1025); any SMTP server in production.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    mail_from: str = "alerts@jobs.local"
    alert_min_score: float = 60.0
    alert_max_jobs_per_email: int = 20
    # Used to build links in emails.
    public_url: str = "http://localhost"

    # Postings not seen by the scraper for this many days are marked inactive (cli.py deactivate-stale).
    stale_days: int = 14
    curriculum_file: Path = Path(__file__).parent / "curriculum.yaml"

    @property
    def is_dev(self) -> bool:
        return self.app_env.lower() == "dev"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _require_secrets_outside_dev(self) -> "Settings":
        if self.is_dev:
            self.secret_key = self.secret_key or DEV_SECRET_KEY
            self.database_url = self.database_url or DEV_DATABASE_URL
            return self
        if not self.secret_key or self.secret_key == DEV_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set to a private random value (APP_ENV is not 'dev'). "
                "For local development set APP_ENV=dev."
            )
        if not self.database_url:
            raise ValueError("DATABASE_URL must be set (APP_ENV is not 'dev').")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
