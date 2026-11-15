from datetime import datetime, timezone
import uuid

from ..db import Database


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def cleanup_expired_llm_cache(db: Database, now: datetime | None = None) -> int:
    cutoff = (now or utc_now()).isoformat()
    cursor = db.execute("DELETE FROM llm_cache WHERE expires_at <= ?", (cutoff,))
    db.commit()
    return cursor.rowcount


def insert_cache_row(db: Database, values: tuple):
    db.execute(
        "INSERT INTO llm_cache (id, cache_key, startup_id, purpose, provider, model, schema_version, temperature, response_text, tokens_in, tokens_out, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), *values),
    )
    db.commit()
