import sqlite3
from pathlib import Path
from typing import Any

from .config import Settings


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.is_remote = bool(settings.turso_database_url)
        if self.is_remote:
            import libsql

            self.connection = libsql.connect(
                database=settings.turso_database_url,
                auth_token=settings.turso_auth_token,
            )
        else:
            path = Path(settings.database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(path, check_same_thread=False)
            self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql: str, params: tuple[Any, ...] = ()):
        return self.connection.execute(sql, params)

    def executescript(self, sql: str):
        if self.is_remote:
            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    self.connection.execute(statement)
        else:
            self.connection.executescript(sql)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


def apply_migrations(db: Database, migrations_dir: Path):
    db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    applied = {row[0] for row in db.execute("SELECT version FROM schema_migrations").fetchall()}
    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in applied:
            continue
        db.executescript(path.read_text())
        db.execute("INSERT INTO schema_migrations (version) VALUES (?)", (path.name,))
        db.commit()
    _repair_legacy_cache_schema(db)


def _repair_legacy_cache_schema(db: Database):
    """Upgrade pre-002 cache tables that were created before provider metadata existed."""
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    if "llm_cache" in tables:
        columns = {row[1] for row in db.execute("PRAGMA table_info(llm_cache)").fetchall()}
        additions = {
            "startup_id": "TEXT REFERENCES startups(id) ON DELETE CASCADE",
            "purpose": "TEXT NOT NULL DEFAULT 'other'",
            "provider": "TEXT NOT NULL DEFAULT 'unknown'",
            "model": "TEXT NOT NULL DEFAULT 'unknown'",
            "schema_version": "TEXT NOT NULL DEFAULT 'legacy'",
            "temperature": "REAL NOT NULL DEFAULT 0",
            "tokens_in": "INTEGER",
            "tokens_out": "INTEGER",
            "created_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "expires_at": "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00'",
        }
        for name, definition in additions.items():
            if name not in columns:
                db.execute(f"ALTER TABLE llm_cache ADD COLUMN {name} {definition}")
        db.execute("CREATE INDEX IF NOT EXISTS idx_llm_cache_lookup ON llm_cache(cache_key, startup_id, expires_at)")
    if "embeddings" in tables:
        columns = {row[1] for row in db.execute("PRAGMA table_info(embeddings)").fetchall()}
        if "chunk_index" not in columns:
            db.execute("ALTER TABLE embeddings ADD COLUMN chunk_index INTEGER NOT NULL DEFAULT 0")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_embeddings_identity_chunk ON embeddings(content_hash, chunk_index, model, revision, dim, startup_id)")
    db.commit()
