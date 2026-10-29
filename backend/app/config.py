"""Application settings loaded from environment variables and the local .env file.

Rules:
- The database password is a SecretStr and is never logged or printed.
- The .env file lives at the repository root and is ignored by Git.
- Settings are cached; tests build their own URL instead of mutating this cache.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Smart Load Protection Panel"
    app_env: str = "development"

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_client_id: str = "smart-panel-backend"

    # 127.0.0.1 instead of "localhost": on Windows, "localhost" resolves to
    # IPv6 ::1 first, but Docker publishes the port on IPv4 only. The failed
    # IPv6 attempt can stall for the full OS timeout before falling back.
    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_name: str = "smart_panel"
    database_user: str = "smart_panel_user"
    # Required: there is no default password anywhere in the codebase.
    database_password: SecretStr

    # Authentication. Empty by default so Alembic can run with database
    # settings only; app startup rejects an empty or short value.
    jwt_secret: SecretStr = SecretStr("")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 14

    # Comma-separated list of allowed dashboard origins.
    cors_origins: str = "http://localhost:5173"

    # Simple in-process login limiter (single-process MVP only).
    login_max_attempts: int = 5
    login_window_seconds: int = 300

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    def database_url(self, database: str | None = None) -> URL:
        """SQLAlchemy URL for PostgreSQL via the psycopg 3 driver.

        Returning a URL object avoids manual quoting of special characters in
        the password.
        """

        return URL.create(
            "postgresql+psycopg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=database or self.database_name,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
