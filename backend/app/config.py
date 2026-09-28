from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings
from sqlalchemy import URL


class Settings(BaseSettings):
    postgres_host: str = "postgres"
    postgres_db: str = "foxelli"
    postgres_user: str = "foxelli"
    postgres_password: str
    redis_url: str = "redis://redis:6379/0"
    upload_dir: Path = Path("/data")
    max_upload_bytes: int = 100 * 1024 * 1024
    max_duration_ms: int = 300_000
    gemini_api_key: SecretStr
    gemini_model: str = "gemini-3.8-flash"
    gemini_prepare_timeout_seconds: int = 300
    gemini_generate_timeout_seconds: int = 120
    gemini_generate_max_output_tokens: int = 8192
    mrq_brandbook_path: Path = Path("/app/reference/mrq.pdf")

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
