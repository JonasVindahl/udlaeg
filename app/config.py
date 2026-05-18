"""Application settings loaded from environment / .env via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./db/udlaeg.db"
    data_dir: Path = Path("./data")
    db_dir: Path = Path("./db")
    secret_key: str = "change-me"
    session_cookie_secure: bool = True
    allowed_hosts: str = "localhost"
    log_level: str = "INFO"
    max_upload_mb: int = 10
    tz: str = "Europe/Copenhagen"

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def receipts_dir(self) -> Path:
        return self.data_dir / "receipts"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
