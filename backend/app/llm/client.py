from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import random
import time
from typing import Any, Callable
import uuid

from pydantic import BaseModel, ValidationError

from ..db import Database
from .cache import cleanup_expired_llm_cache, insert_cache_row
from .configuration import LLMConfig, Route
from .limiter import ModelCircuitBreaker, ProviderBudgetExceeded, ProviderLimiter
from .privacy import message_metadata, stable_hash
from .providers import OpenAICompatibleProvider, Provider, ProviderException, ProviderResponse


class AllProvidersFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class CompletionResult:
    value: Any
    provider: str
    model: str
    tokens_in: int | None
    tokens_out: int | None
    cache_hit: bool
    latency_ms: int
    total_latency_ms: int

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cache_hit": self.cache_hit,
            "latency_ms": self.latency_ms,
            "total_latency_ms": self.total_latency_ms,
        }


class LLMClient:
    def __init__(
        self,
        db: Database,
        config: LLMConfig | None = None,
        providers: dict[tuple[str, str], Provider] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        random_fn: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.db = db
        self.config = config or LLMConfig.load()
        self.providers = providers or {}
        self.sleeper = sleeper
        self.random_fn = random_fn
        self.clock = clock
        self.limiter = ProviderLimiter()
        self.circuit = ModelCircuitBreaker(self.config.circuit_failure_count, self.config.circuit_cooldown_seconds, clock)
        self.logger = logging.getLogger("carmine.llm.debug")

    def _provider(self, route: Route) -> Provider:
        key = (route.provider, route.model)
        if key not in self.providers:
            config = self.config.providers[route.provider]
            api_key = self.config.api_keys.get(route.provider) or os.getenv(config.api_key_env)
            if not api_key:
                raise ProviderException(f"missing API key environment variable {config.api_key_env}")
            self.providers[key] = OpenAICompatibleProvider(api_key, config.base_url)
        return self.providers[key]

    def _log(self, *, run_id: str | None, provider: str, model: str, purpose: str, tokens_in: int | None, tokens_out: int | None, cache_hit: bool, latency_ms: int, error: str | None, http_status: int | None = None):
        self.db.execute(
            "INSERT INTO llm_calls (id, run_id, provider, model, purpose, tokens_in, tokens_out, cache_hit, latency_ms, error, http_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), run_id, provider, model, purpose, tokens_in, tokens_out, int(cache_hit), latency_ms, error, http_status),
        )
        self.db.commit()

    def _cache_key(self, purpose: str, model: str, messages: list[dict[str, str]], schema: type[BaseModel] | None, temperature: float) -> str:
        return stable_hash({
            "purpose": purpose,
            "model": model,
            "messages": messages,
            "schema_version": self.config.schema_version,
            "schema": schema.model_json_schema() if schema else None,
            "temperature": temperature,
        })

    def _cached(self, cache_key: str, startup_id: str | None, now: datetime):
        if startup_id is None:
            row = self.db.execute(
                "SELECT id, response_text, tokens_in, tokens_out, provider, model FROM llm_cache WHERE cache_key = ? AND startup_id IS NULL AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
                (cache_key, now.isoformat()),
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT id, response_text, tokens_in, tokens_out, provider, model FROM llm_cache WHERE cache_key = ? AND startup_id = ? AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
                (cache_key, startup_id, now.isoformat()),
            ).fetchone()
        return row

    @staticmethod
    def _response_format(schema: type[BaseModel] | None) -> dict[str, Any] | None:
        if not schema:
            return None
        json_schema = schema.model_json_schema()

        def make_objects_strict(value: Any):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    value["additionalProperties"] = False
                for child in value.values():
                    make_objects_strict(child)
            elif isinstance(value, list):
                for child in value:
                    make_objects_strict(child)

        make_objects_strict(json_schema)
        return {"type": "json_schema", "json_schema": {"name": "carmine_output", "strict": True, "schema": json_schema}}

    @staticmethod
    def _validation_summary(exc: ValidationError | json.JSONDecodeError) -> str:
        if isinstance(exc, ValidationError):
            return "validation_error:" + ",".join(str(error.get("type", "unknown")) for error in exc.errors())
        return "invalid_json"

    def _delay(self, retry_number: int, retry_after: float | None, waited: float) -> float:
        remaining = self.config.max_total_wait_seconds - waited
        if remaining <= 0:
            return 0
        base = retry_after if retry_after is not None else min(2 ** retry_number, 8) + self.random_fn()
        return min(base, remaining)

    def _parse(self, text: str, schema: type[BaseModel] | None):
        if not schema:
            return text
        try:
            return schema.model_validate_json(text)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ValueError(self._validation_summary(exc)) from exc

    def complete(
        self,
        purpose: str,
        messages: list[dict[str, str]],
        schema: type[BaseModel] | None = None,
        *,
        temperature: float = 0.0,
        startup_id: str | None = None,
        run_id: str | None = None,
        bypass_cache: bool = False,
        routes_override: tuple[Route, ...] | None = None,
    ) -> CompletionResult:
        if purpose not in self.config.routes:
            raise ValueError(f"unknown purpose: {purpose}")
        candidate_routes = routes_override or self.config.routes[purpose]
        if purpose != "verify" and any(route.provider == "groq" for route in candidate_routes):
            raise ValueError("Groq is permitted only for verify")
        cleanup_expired_llm_cache(self.db)
        timeout = self.config.timeouts[purpose]
        total_started = self.clock()
        deadline = total_started + timeout.total_seconds
        failures: list[str] = []
        repair_used: set[tuple[str, str]] = set()
        repair_errors: dict[tuple[str, str], str] = {}
        waited = 0.0
        for route in candidate_routes:
            model_key = (route.provider, route.model)
            if self.circuit.is_open(model_key):
                failures.append(f"{route.provider}/{route.model}: circuit_open")
                continue
            cache_key = self._cache_key(purpose, route.model, messages, schema, temperature)
            if not bypass_cache:
                row = self._cached(cache_key, startup_id, datetime.now(timezone.utc))
                if row:
                    started = time.perf_counter()
                    try:
                        value = self._parse(row[1], schema)
                    except ValueError:
                        self.db.execute("DELETE FROM llm_cache WHERE id = ?", (row[0],))
                        self.db.commit()
                    else:
                        latency = int((time.perf_counter() - started) * 1000)
                        self._log(run_id=run_id, provider=row[4], model=row[5], purpose=purpose, tokens_in=row[2], tokens_out=row[3], cache_hit=True, latency_ms=latency, error=None, http_status=200)
                        return CompletionResult(value, row[4], row[5], row[2], row[3], True, latency, latency)
            try:
                provider = self._provider(route)
            except ProviderException as exc:
                self._log(run_id=run_id, provider=route.provider, model=route.model, purpose=purpose, tokens_in=None, tokens_out=None, cache_hit=False, latency_ms=0, error=str(exc))
                failures.append(f"{route.provider}/{route.model}: {exc}")
                continue
            provider_config = self.config.providers[route.provider]
            overload_retries = 0
            for attempt in range(self.config.max_attempts_per_provider):
                remaining = deadline - self.clock()
                if remaining <= 0:
                    failures.append(f"{route.provider}/{route.model}: total_deadline_exceeded")
                    break
                if self.circuit.is_open(model_key):
                    failures.append(f"{route.provider}/{route.model}: circuit_open")
                    break
                try:
                    self.limiter.reserve(route.provider, provider_config.requests_per_minute, provider_config.tokens_per_minute, sum(len(message.get("content", "")) for message in messages), self.db, provider_config.daily_requests, provider_config.daily_tokens)
                except ProviderBudgetExceeded as exc:
                    self._log(run_id=run_id, provider=route.provider, model=route.model, purpose=purpose, tokens_in=None, tokens_out=None, cache_hit=False, latency_ms=0, error=str(exc))
                    failures.append(f"{route.provider}/{route.model}: {exc}")
                    break
                started = time.perf_counter()
                current_messages = messages
                if (route.provider, route.model) in repair_used:
                    current_messages = [*messages, {"role": "user", "content": f"Return valid JSON matching the schema. Correct this validation failure and output JSON only: {repair_errors[(route.provider, route.model)]}"}]
                try:
                    if self.config.debug_local:
                        self.logger.debug("llm_debug provider=%s model=%s messages=%r", route.provider, route.model, current_messages)
                    response: ProviderResponse = provider.complete(model=route.model, messages=current_messages, response_format=self._response_format(schema), temperature=temperature, timeout_seconds=min(timeout.attempt_seconds, remaining))
                    latency = int((time.perf_counter() - started) * 1000)
                    try:
                        value = self._parse(response.text, schema)
                    except ValueError as exc:
                        self._log(run_id=run_id, provider=route.provider, model=route.model, purpose=purpose, tokens_in=response.tokens_in, tokens_out=response.tokens_out, cache_hit=False, latency_ms=latency, error=str(exc), http_status=response.http_status)
                        failures.append(f"{route.provider}/{route.model}: {exc}")
                        if schema and (route.provider, route.model) not in repair_used:
                            repair_errors[(route.provider, route.model)] = str(exc)
                            repair_used.add((route.provider, route.model))
                            continue
                        break
                    if self.config.debug_local:
                        self.logger.debug("llm_debug provider=%s model=%s response=%r", route.provider, route.model, response.text)
                    self.circuit.record_success(model_key)
                    self._log(run_id=run_id, provider=route.provider, model=route.model, purpose=purpose, tokens_in=response.tokens_in, tokens_out=response.tokens_out, cache_hit=False, latency_ms=latency, error=None, http_status=response.http_status)
                    expires = datetime.now(timezone.utc) + timedelta(seconds=self.config.cache_ttl_seconds)
                    insert_cache_row(self.db, (cache_key, startup_id, purpose, route.provider, route.model, self.config.schema_version, temperature, response.text, response.tokens_in, response.tokens_out, expires.isoformat()))
                    return CompletionResult(value, route.provider, route.model, response.tokens_in, response.tokens_out, False, latency, int((self.clock() - total_started) * 1000))
                except (ProviderException, TimeoutError) as exc:
                    latency = int((time.perf_counter() - started) * 1000)
                    status = getattr(exc, "status_code", None)
                    retryable = isinstance(exc, TimeoutError) or getattr(exc, "timed_out", False) or status == 429 or (status is not None and status >= 500)
                    overload = status in (429, 503) or any(word in str(exc).lower() for word in ("overloaded", "high demand", "temporarily unavailable"))
                    error = f"{type(exc).__name__}:{status}:{exc}" if status else f"{type(exc).__name__}:{exc}"
                    self._log(run_id=run_id, provider=route.provider, model=route.model, purpose=purpose, tokens_in=None, tokens_out=None, cache_hit=False, latency_ms=latency, error=error, http_status=status)
                    failures.append(f"{route.provider}/{route.model}: {error}")
                    if overload:
                        self.circuit.record_overload(model_key)
                        overload_retries += 1
                        if overload_retries > self.config.max_overload_retries:
                            break
                    if not retryable or attempt + 1 >= self.config.max_attempts_per_provider:
                        break
                    delay = min(self._delay(attempt, getattr(exc, "retry_after", None), waited), max(0.0, deadline - self.clock()))
                    if delay <= 0:
                        break
                    self.sleeper(delay)
                    waited += delay
        raise AllProvidersFailed(f"all configured providers failed after {int((self.clock() - total_started) * 1000)}ms: " + "; ".join(failures))

    def probe(self, route: Route, schema: type[BaseModel] | None = None) -> CompletionResult:
        purpose = "verify" if route.provider == "groq" else "other"
        return self.complete(purpose, [{"role": "user", "content": "Return a JSON object with the boolean field ok set to true."}], schema, bypass_cache=True, routes_override=(route,))
