from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    turso_database_url: str = ""
    turso_auth_token: str = ""
    database_path: str = "data/carmine.db"
    cors_origins: str = "http://localhost:5173"
    llm_config_path: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=(
            str(Path(__file__).resolve().parents[1] / ".env"),
            str(Path(__file__).resolve().parents[2] / ".env"),
        ),
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
