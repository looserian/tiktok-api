from typing import Set
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_KEYS: str = ""
    LOG_LEVEL: str = "INFO"
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    PLAYWRIGHT_HEADLESS: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_api_keys(self) -> Set[str]:
        """Parse comma-separated API_KEYS into a set of clean strings."""
        if not self.API_KEYS:
            return set()
        return {key.strip() for key in self.API_KEYS.split(",") if key.strip()}


settings = Settings()
