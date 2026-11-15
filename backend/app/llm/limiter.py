from collections import deque
from datetime import datetime, timedelta, timezone
from threading import Lock

from ..db import Database


class ProviderBudgetExceeded(Exception):
    pass


class ModelCircuitBreaker:
    def __init__(self, failure_count: int, cooldown_seconds: float, clock):
        self.failure_count = failure_count
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self._states: dict[tuple[str, str], tuple[int, float]] = {}

    def is_open(self, model_key: tuple[str, str]) -> bool:
        state = self._states.get(model_key)
        if not state:
            return False
        _, opened_until = state
        if opened_until and self.clock() < opened_until:
            return True
        if opened_until:
            self._states.pop(model_key, None)
        return False

    def record_overload(self, model_key: tuple[str, str]):
        failures, _ = self._states.get(model_key, (0, 0.0))
        failures += 1
        if failures >= self.failure_count:
            self._states[model_key] = (failures, self.clock() + self.cooldown_seconds)
        else:
            self._states[model_key] = (failures, 0.0)

    def record_success(self, model_key: tuple[str, str]):
        self._states.pop(model_key, None)


class ProviderLimiter:
    def __init__(self):
        self._events: dict[str, deque[tuple[datetime, int]]] = {}
        self._lock = Lock()

    def reserve(self, provider: str, requests_per_minute: int, tokens_per_minute: int, estimated_tokens: int, db: Database, daily_requests: int, daily_tokens: int):
        now = datetime.now(timezone.utc)
        with self._lock:
            events = self._events.setdefault(provider, deque())
            cutoff = now - timedelta(minutes=1)
            while events and events[0][0] < cutoff:
                events.popleft()
            if requests_per_minute and len(events) >= requests_per_minute:
                raise ProviderBudgetExceeded(f"{provider} requests-per-minute limit reached")
            used_tokens = sum(tokens for _, tokens in events)
            if tokens_per_minute and used_tokens + estimated_tokens > tokens_per_minute:
                raise ProviderBudgetExceeded(f"{provider} tokens-per-minute limit reached")
            today = now.date().isoformat()
            row = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(COALESCE(tokens_in, 0) + COALESCE(tokens_out, 0)), 0) FROM llm_calls WHERE provider = ? AND date(created_at) = ?",
                (provider, today),
            ).fetchone()
            if daily_requests and row[0] >= daily_requests:
                raise ProviderBudgetExceeded(f"{provider} daily request limit reached")
            if daily_tokens and row[1] + estimated_tokens > daily_tokens:
                raise ProviderBudgetExceeded(f"{provider} daily token limit reached")
            events.append((now, estimated_tokens))
