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
