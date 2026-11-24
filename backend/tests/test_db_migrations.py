from pathlib import Path

from app.config import Settings
from app.db import Database, apply_migrations


def test_migrations_repair_legacy_llm_cache_schema(tmp_path):
    settings = Settings(database_path=str(tmp_path / "legacy.db"), turso_database_url="", turso_auth_token="")
    db = Database(settings)
    db.executescript((Path(__file__).parents[1] / "app" / "migrations" / "001_initial.sql").read_text())
    db.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    db.execute("INSERT INTO schema_migrations (version) VALUES ('001_initial.sql')")
    db.executescript("""
    CREATE TABLE llm_cache (
      id TEXT PRIMARY KEY, cache_key TEXT NOT NULL, startup_id TEXT,
      purpose TEXT NOT NULL, response_text TEXT NOT NULL,
      expires_at TEXT NOT NULL
    );
    """)
    db.commit()
    apply_migrations(db, Path(__file__).parents[1] / "app" / "migrations")
    columns = {row[1] for row in db.execute("PRAGMA table_info(llm_cache)").fetchall()}
    assert {"provider", "model", "schema_version", "temperature", "tokens_in", "tokens_out"} <= columns
    db.execute("INSERT INTO llm_cache (id, cache_key, purpose, provider, model, schema_version, temperature, response_text, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ("x", "k", "other", "gemini", "model", "1", 0, "{}", "2099-01-01T00:00:00+00:00"))
    db.commit()
