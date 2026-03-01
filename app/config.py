from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Profile Intelligence Engine"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/profile_engine"
    )
    request_timeout_seconds: float = 8.0
    google_cse_api_key: Optional[str] = None
    google_cse_cx: Optional[str] = None

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4.1-mini"
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3-flash"
    script_generation_max_attempts: int = 4
    llm_reflection_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
