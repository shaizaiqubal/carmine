import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import time

import pytest

from app.config import Settings
from app.llm.client import LLMClient
from app.llm.configuration import LLMConfig, Route


EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "docs"
RUN_REAL = os.getenv("CARMINE_RUN_REAL_LLM_DEMOS") == "1"


def _require_real_keys(config):
    if not RUN_REAL:
        pytest.skip("set CARMINE_RUN_REAL_LLM_DEMOS=1 to run real-provider demos")
    missing = [name for name in ("gemini", "groq") if not config.api_keys.get(name)]
    if missing:
        pytest.skip(f"missing configured key(s): {', '.join(missing)}")


def _write_evidence(filename, title, rows):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    columns = ["id", "provider", "model", "purpose", "cache_hit", "latency_ms", "error", "created_at"]
    lines = [title, "=" * len(title), " | ".join(columns)]
    for row in rows:
        values = []
        for column in columns:
            value = row[column] if row[column] is not None else ""
            if column == "created_at" and value:
                value = datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
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


def test_real_cache_hit(client):
    config = LLMConfig.load(settings=Settings())
    _require_real_keys(config)
    prompt = f"Reply with exactly cache-demo-ok. nonce={time.time_ns()}"
    service = LLMClient(client.db, config=config)
    route = (Route("gemini", "gemini-3.5-flash-lite"),)
    messages = [{"role": "user", "content": prompt}]

    first = service.complete("extract", messages, routes_override=route)
    cache_count_after_first = client.db.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
    second = service.complete("extract", messages, routes_override=route)
    rows = _rows_for(client.db, "extract")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.value == second.value
    assert first.latency_ms > 0
    assert rows[-1]["cache_hit"] == 1
    assert rows[-1]["latency_ms"] <= 5
    assert cache_count_after_first == 1
    assert client.db.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0] == 1

    _write_evidence("llm_demo_cache.txt", "LLM demo: real Gemini cache hit", rows)
    print("PASS real_cache_hit")


def test_real_forced_gemini_fallback_to_groq(client):
    config = LLMConfig.load(settings=Settings())
    _require_real_keys(config)
    original_gemini_key = config.api_keys["gemini"]
    invalidated_config = replace(
        config,
        api_keys={**config.api_keys, "gemini": "invalid-for-this-call-only"},
        max_attempts_per_provider=1,
        max_overload_retries=0,
        max_total_wait_seconds=20,
    )
    service = LLMClient(client.db, config=invalidated_config)
    routes = (
        Route("gemini", "gemini-3.5-flash-lite"),
        Route("groq", "openai/gpt-oss-120b"),
    )
    prompt = f"Reply with exactly fallback-demo-ok. nonce={time.time_ns()}"

    result = service.complete("verify", [{"role": "user", "content": prompt}], routes_override=routes)
    rows = _rows_for(client.db, "verify")
    gemini_rows = [row for row in rows if row["provider"] == "gemini"]
    groq_rows = [row for row in rows if row["provider"] == "groq"]

    assert config.api_keys["gemini"] == original_gemini_key
    assert result.provider == "groq"
    assert result.model == "openai/gpt-oss-120b"
    assert result.value
    assert len(gemini_rows) == 1
    assert gemini_rows[0]["error"]
    assert len(groq_rows) == 1
    assert groq_rows[0]["error"] is None
    assert groq_rows[0]["cache_hit"] == 0
    assert groq_rows[0]["latency_ms"] > 0

    _write_evidence("llm_demo_fallback.txt", "LLM demo: real Gemini to Groq fallback", rows)
    print("PASS real_forced_fallback")
