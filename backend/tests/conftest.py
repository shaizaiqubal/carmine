import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.auth import AuthUser, get_auth_user
from app.config import Settings
from app.db import Database
from app.main import make_app


@pytest.fixture
def client():
    test_settings = Settings(
        database_path=":memory:",
        supabase_url="",
        supabase_anon_key="",
        turso_database_url="",
        turso_auth_token="",
    )
    db = Database(test_settings)
    app = make_app(test_settings, db)
    current = {"user": AuthUser("user-a", "a@example.com")}
    app.dependency_overrides[get_auth_user] = lambda: current["user"]
    with TestClient(app) as test_client:
        test_client.current_user = current
        test_client.db = db
        yield test_client
    db.close()
