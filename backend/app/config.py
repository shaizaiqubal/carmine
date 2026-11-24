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
    assumption_extract_max_chars: int = 20000
    llm_interactive_rate_limit_per_minute: int = 5
    runs_per_startup_per_day: int = 1
    retrieval_search_cache_ttl_seconds: int = 900
    retrieval_fetch_cache_ttl_seconds: int = 86400
    retrieval_robots_cache_ttl_seconds: int = 86400
    retrieval_per_domain_delay_seconds: float = 1.0
    retrieval_http_timeout_seconds: float = 15.0
    retrieval_max_retries: int = 2
    retrieval_max_response_bytes: int = 5_000_000
    retrieval_max_text_chars: int = 40_000
    retrieval_max_snippet_chars: int = 2_000
    retrieval_user_agent: str = "Carmine/0.1 (+https://github.com/carmine)"
    stackexchange_key: str = ""

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
