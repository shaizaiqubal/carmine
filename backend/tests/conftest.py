import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.auth import AuthUser, get_auth_user
from app.config import Settings
from app.db import Database
from app.main import make_app


@pytest.fixture
def client():
    db = Database(Settings(database_path=":memory:"))
    app = make_app(Settings(database_path=":memory:"), db)
    current = {"user": AuthUser("user-a", "a@example.com")}
    app.dependency_overrides[get_auth_user] = lambda: current["user"]
    with TestClient(app) as test_client:
        test_client.current_user = current
        yield test_client
    db.close()
