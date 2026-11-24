from dataclasses import dataclass
from pathlib import Path
import os
import tomllib

from ..config import Settings


PURPOSES = {"query_plan", "extract", "verify", "rank_brief", "assumption_extract", "counter", "other"}


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str
    requests_per_minute: int
    tokens_per_minute: int
    daily_requests: int
    daily_tokens: int


@dataclass(frozen=True)
class Route:
    provider: str
    model: str


@dataclass(frozen=True)
class PurposeTimeout:
    attempt_seconds: float
    total_seconds: float


@dataclass(frozen=True)
class LLMConfig:
    providers: dict[str, ProviderConfig]
    routes: dict[str, tuple[Route, ...]]
    cache_ttl_seconds: int
    max_attempts_per_provider: int
    max_overload_retries: int
    max_total_wait_seconds: float
    circuit_failure_count: int
    circuit_cooldown_seconds: float
    timeouts: dict[str, PurposeTimeout]
    schema_version: str
    debug_local: bool
    api_keys: dict[str, str]
    embedding_model: str
    embedding_revision: str
    embedding_dim: int

    @classmethod
    def load(cls, path: Path | None = None, settings: Settings | None = None) -> "LLMConfig":
        settings_obj = settings or Settings()
        configured_path = settings_obj.llm_config_path or os.getenv("LLM_CONFIG_PATH", "")
        if configured_path and not Path(configured_path).is_absolute():
            configured_path = str(Path(__file__).resolve().parents[2] / configured_path)
        config_path = path or Path(configured_path or Path(__file__).with_name("config.toml"))
        raw = tomllib.loads(config_path.read_text())
        settings = raw["settings"]
        providers = {
            name: ProviderConfig(
                name=name,
                base_url=data["base_url"],
                api_key_env=data["api_key_env"],
                requests_per_minute=int(data["requests_per_minute"]),
                tokens_per_minute=int(data["tokens_per_minute"]),
                daily_requests=int(data["daily_requests"]),
                daily_tokens=int(data["daily_tokens"]),
            )
            for name, data in raw["providers"].items()
        }
        routes = {
            purpose: tuple(Route(provider=pair[0], model=pair[1]) for pair in data["pairs"])
            for purpose, data in raw["routes"].items()
        }
        for purpose in PURPOSES:
            override = os.getenv(f"LLM_ROUTE_{purpose.upper()}")
            if override:
                routes[purpose] = tuple(
                    Route(provider=pair.split(":", 1)[0], model=pair.split(":", 1)[1])
                    for pair in override.split(",")
                )
        if set(routes) != PURPOSES:
            raise ValueError(f"routes must cover exactly {sorted(PURPOSES)}")
        for purpose, pairs in routes.items():
            for pair in pairs:
                if pair.provider not in providers:
                    raise ValueError(f"unknown provider {pair.provider} in {purpose}")
                if pair.provider == "groq" and purpose != "verify":
                    raise ValueError("Groq is permitted only for verify")
        timeouts = {
            purpose: PurposeTimeout(float(data["attempt_seconds"]), float(data["total_seconds"]))
            for purpose, data in raw["timeouts"].items()
        }
        if set(timeouts) != PURPOSES:
            raise ValueError(f"timeouts must cover exactly {sorted(PURPOSES)}")
        debug_local = os.getenv("LLM_DEBUG_LOCAL", str(settings["debug_local"])).lower() == "true"
        environment = os.getenv("CARMINE_ENV", os.getenv("ENVIRONMENT", "development")).lower()
        if debug_local and environment in {"prod", "production"}:
            raise ValueError("LLM_DEBUG_LOCAL is forbidden in production")
        return cls(
            providers=providers,
            routes=routes,
            cache_ttl_seconds=int(os.getenv("LLM_CACHE_TTL_SECONDS", settings["cache_ttl_seconds"])),
            max_attempts_per_provider=int(os.getenv("LLM_MAX_ATTEMPTS", settings["max_attempts_per_provider"])),
            max_overload_retries=int(os.getenv("LLM_MAX_OVERLOAD_RETRIES", settings["max_overload_retries"])),
            max_total_wait_seconds=float(os.getenv("LLM_MAX_TOTAL_WAIT_SECONDS", settings["max_total_wait_seconds"])),
            circuit_failure_count=int(os.getenv("LLM_CIRCUIT_FAILURE_COUNT", settings["circuit_failure_count"])),
            circuit_cooldown_seconds=float(os.getenv("LLM_CIRCUIT_COOLDOWN_SECONDS", settings["circuit_cooldown_seconds"])),
            timeouts=timeouts,
            schema_version=str(settings["schema_version"]),
            debug_local=debug_local,
            api_keys={
                name: getattr(settings_obj, provider.api_key_env.lower(), "") or os.getenv(provider.api_key_env, "")
                for name, provider in providers.items()
            },
            embedding_model=raw["embeddings"]["model"],
            embedding_revision=raw["embeddings"]["revision"],
            embedding_dim=int(raw["embeddings"]["dim"]),
        )
