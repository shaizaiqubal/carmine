from pathlib import Path

import pytest

from app.config import Settings
from app.db import Database, apply_migrations
from app.retrieval import RetrievalService


feedparser = pytest.importorskip("feedparser")


def test_rss_matches_content_and_any_query_keyword(monkeypatch):
    settings = Settings(database_path=":memory:", turso_database_url="", turso_auth_token="", retrieval_per_domain_delay_seconds=0)
    db = Database(settings)
    apply_migrations(db, Path(__file__).parents[1] / "app" / "migrations")
    service = RetrievalService(db, settings, sleeper=lambda _: None)
    monkeypatch.setattr(service, "request_bytes", lambda _: b'''<rss version="2.0"><channel><item><title>Validation</title><link>https://example.com/a</link><content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/"><![CDATA[Useful startup material]]></content:encoded></item></channel></rss>''')
    hits = service.search("rss", "startup validation", 10, feeds=["https://feed.test/rss"])
    assert len(hits) == 1
