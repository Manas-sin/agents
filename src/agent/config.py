from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: Literal["anthropic", "openai", "gemini", "fake"] = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None

    honcho_api_key: str | None = None
    honcho_app_name: str = "agent-app"

    memory_file_path: str = ".infi-memory.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
