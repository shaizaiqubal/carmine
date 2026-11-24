from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import time

from app.llm.client import LLMClient
from app.llm.configuration import LLMConfig, Route
from app.llm.providers import ProviderException, ProviderResponse


EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "docs"


class DemoProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _write_evidence(filename, title, rows):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    columns = ["id", "provider", "model", "purpose", "cache_hit", "latency_ms", "error", "created_at"]
    lines = [title, "=" * len(title), " | ".join(columns)]
    for row in rows:
        values = []
        for column in columns:
            value = row[column] if row[column] is not None else ""
            if column == "created_at" and value:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                value = parsed.strftime("%Y-%m-%d %H:%M:%S")
            values.append(str(value))
        lines.append(" | ".join(values))
    (EVIDENCE_DIR / filename).write_text("\n".join(lines) + "\n")


def _rows_for(db, purpose):
    return [
        dict(row)
        for row in db.execute(
            "SELECT id, provider, model, purpose, cache_hit, latency_ms, error, created_at "
            "FROM llm_calls WHERE purpose = ? ORDER BY created_at, rowid",
            (purpose,),
        ).fetchall()
    ]


def test_demo_cache_hit(client):
    prompt = f"cache demo {time.time_ns()}"
    provider = DemoProvider([ProviderResponse("cache-demo-answer", 3, 2)])
    service = LLMClient(
        client.db,
        providers={("gemini", "demo-cache-model"): provider},
    )
    routes = (Route("gemini", "demo-cache-model"),)
    messages = [{"role": "user", "content": prompt}]

    first = service.complete("other", messages, routes_override=routes)
    cache_rows_after_first = client.db.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
    second = service.complete("other", messages, routes_override=routes)
    rows = _rows_for(client.db, "other")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.value == second.value == "cache-demo-answer"
    assert provider.calls == 1
    assert cache_rows_after_first == 1
    assert client.db.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0] == 1
    assert rows[-1]["cache_hit"] == 1
    assert rows[-1]["error"] is None
    assert rows[-1]["latency_ms"] <= 5

    _write_evidence("llm_demo_cache_stub.txt", "LLM demo: stub cache hit", rows)
    print("PASS cache_hit")


def test_demo_forced_fallback(client):
    prompt = f"fallback demo {time.time_ns()}"
    primary = DemoProvider([
        ProviderException("forced demo primary failure", status_code=503),
        ProviderException("forced demo primary failure", status_code=503),
    ])
    fallback = DemoProvider([ProviderResponse("fallback-demo-answer", 4, 2)])
    base_config = LLMConfig.load()
    config = replace(
        base_config,
        max_attempts_per_provider=2,
        max_overload_retries=1,
        max_total_wait_seconds=0.1,
    )
    service = LLMClient(
        client.db,
        config=config,
        providers={
            ("gemini", "demo-primary-model"): primary,
            ("gemini", "demo-fallback-model"): fallback,
        },
        sleeper=lambda _: None,
        random_fn=lambda: 0,
    )
    routes = (
        Route("gemini", "demo-primary-model"),
        Route("gemini", "demo-fallback-model"),
    )

    result = service.complete("other", [{"role": "user", "content": prompt}], routes_override=routes)
    rows = _rows_for(client.db, "other")
    primary_rows = [row for row in rows if row["model"] == "demo-primary-model"]
    fallback_rows = [row for row in rows if row["model"] == "demo-fallback-model"]

    assert result.value == "fallback-demo-answer"
    assert result.model == "demo-fallback-model"
    assert primary.calls == 2
    assert len(primary_rows) == 2
    assert all(row["error"] for row in primary_rows)
    assert len(fallback_rows) == 1
    assert fallback_rows[0]["error"] is None
    assert fallback_rows[0]["cache_hit"] == 0

    _write_evidence("llm_demo_fallback_stub.txt", "LLM demo: stub forced fallback", rows)
    print("PASS forced_fallback")
