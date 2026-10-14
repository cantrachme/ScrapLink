
import re
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "ScrapLink"
    APP_ENV: str = "development"
    DEBUG: bool = True

    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000

    DATABASE_URL: str = ""


    # PostgreSQL
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "scraplink"
    POSTGRES_USER: str = "scraplink"
    POSTGRES_PASSWORD: str = ""


    ASHBY_BOARDS: list[str] = ["ashby"]
    GREENHOUSE_BOARDS: list[str] = ["anthropic"]
    LEVER_BOARDS: list[str] = ["palantir"]
    USAJOBS_EMAIL: str = ""
    USAJOBS_API_KEY: str = ""
    REMOTIVE_CACHE_PATH: str = ".cache/remotive.json"
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT_MS: int = 20000
    FRONTEND_URL: str = "http://localhost:8000"

    @field_validator("ASHBY_BOARDS", "GREENHOUSE_BOARDS", "LEVER_BOARDS")
    @classmethod
    def board_tokens(cls, values):
        if len(values) > 3 or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", v) for v in values):
            raise ValueError("Configure at most three valid public employer board tokens per platform")
        return list(dict.fromkeys(values))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
