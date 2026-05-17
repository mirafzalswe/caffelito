"""Application settings loaded from environment / .env file.

Single source of truth for runtime configuration. Imported as a singleton
``settings`` instance — no other module should call ``os.getenv`` directly.
"""

from __future__ import annotations

from datetime import time
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_env: Literal["local", "dev", "staging", "prod"] = "local"
    app_debug: bool = False
    app_log_level: str = "INFO"

    # ---- Database ----
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/coffee_loyalty"
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    # ---- Redis ----
    redis_url: str = "redis://127.0.0.1:6379/0"

    # ---- Telegram ----
    customer_bot_token: SecretStr | None = None
    staff_bot_token: SecretStr | None = None
    customer_bot_webhook_url: str | None = None
    staff_bot_webhook_url: str | None = None
    telegram_webhook_secret: SecretStr = SecretStr("change-me")

    # ---- Security ----
    security_pepper: SecretStr = SecretStr("change-me-pepper")
    jwt_secret: SecretStr = SecretStr("change-me-jwt")
    jwt_ttl_seconds: int = 3600

    # ---- Defaults ----
    default_timezone: str = "UTC"
    default_language: str = "ru"
    default_currency: str = "UZS"

    # ---- Loyalty ----
    punchcard_default_expires_days: int = 90
    punchcard_default_cooldown_min: int = 2
    prepaid_default_expires_days: int = 180

    # ---- Notifications / rate ----
    telegram_global_rps: int = 25
    telegram_per_chat_rps: int = 1

    quiet_hours_from: time = time(22, 0)
    quiet_hours_to: time = time(8, 0)

    # ---- Derived helpers ----

    @field_validator("default_currency")
    @classmethod
    def _currency_uppercase(cls, v: str) -> str:
        if len(v) != 3:
            raise ValueError("currency must be a 3-letter ISO code")
        return v.upper()

    @model_validator(mode="after")
    def _enforce_real_secrets_in_prod(self) -> "Settings":
        """Refuse to boot prod/staging with placeholder secrets.

        Catches the classic "shipped .env.example to prod" mistake — with
        ``jwt_secret='change-me-jwt'`` anyone could forge an admin session.
        """
        if self.app_env in ("staging", "prod"):
            bad: list[str] = []
            for field_name in ("jwt_secret", "security_pepper", "telegram_webhook_secret"):
                value = getattr(self, field_name).get_secret_value()
                if value.startswith("change-me"):
                    bad.append(field_name)
            if bad:
                raise ValueError(
                    f"Refusing to start in app_env={self.app_env!r}: "
                    f"these secrets still hold placeholder defaults: {bad}. "
                    f"Set strong values via env vars before boot."
                )
        return self

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic (psycopg / psycopg2)."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
