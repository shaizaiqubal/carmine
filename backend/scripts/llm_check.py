import sys
import time
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.config import Settings
from app.db import Database, apply_migrations
from app.llm.client import LLMClient
from app.llm.configuration import LLMConfig


class ProbeOutput(BaseModel):
    ok: bool


settings = Settings()
db = Database(settings)
apply_migrations(db, Path(__file__).parents[1] / "app" / "migrations")
config = LLMConfig.load(settings=settings)
client = LLMClient(db, config=config)
seen = set()
for purpose, routes in config.routes.items():
    for route in routes:
        if (route.provider, route.model) in seen:
            continue
        seen.add((route.provider, route.model))
        started = time.perf_counter()
        try:
            result = client.probe(route, ProbeOutput)
            print(f"{route.provider}/{route.model}: success total_latency_ms={result.total_latency_ms} attempt_latency_ms={result.latency_ms} tokens_in={result.tokens_in} tokens_out={result.tokens_out}")
        except Exception as exc:
            print(f"{route.provider}/{route.model}: failure latency_ms={int((time.perf_counter() - started) * 1000)} error={str(exc)[:500]}")
db.close()
