from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.db import Database, apply_migrations
from app.retrieval import RetrievalService, normalize_url
from app.retrieval.types import SearchHit
from app.retrieval.types import Document
from app.retrieval import connectors


def service():
    settings = Settings(database_path=":memory:", turso_database_url="", turso_auth_token="", retrieval_per_domain_delay_seconds=0)
    db = Database(settings)
    apply_migrations(db, Path(__file__).parents[1] / "app" / "migrations")
    return RetrievalService(db, settings, sleeper=lambda _: None)


def test_normalize_url_removes_tracking_and_fragment():
    assert normalize_url("HTTPS://Example.COM/a?utm_source=x&b=2&fbclid=y#quote") == "https://example.com/a?b=2"


def test_search_cache_and_direct_api_source(monkeypatch):
    svc = service()
    calls = []
    monkeypatch.setattr(svc, "request_json", lambda *args, **kwargs: (calls.append(1) or {"hits": [{"objectID": "1", "title": "Story", "url": "https://example.com/x", "story_text": "Exact API text"}]}))
    first = svc.search("hn", "query", 2)
    second = svc.search("hn", "query", 2)
    assert len(first) == len(second) == 1 and len(calls) == 1
    assert svc.fetch(first[0].url).text == "Exact API text"
    assert svc.db.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 3


def test_unchanged_content_is_not_new(monkeypatch):
    svc = service()
    response = httpx.Response(200, headers={"content-type": "text/html"}, content=b"fixture")
    monkeypatch.setattr(svc, "_robots_allowed", lambda *_: True)
    monkeypatch.setattr(svc, "_request", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(svc, "_extract", lambda *_: ("same cleaned text", None))
    first = svc.fetch("https://example.com/a?utm_campaign=x")
    svc.settings.retrieval_fetch_cache_ttl_seconds = 0
    second = svc.fetch("https://example.com/a#fragment")
    assert first.is_new is True and second.is_new is False and first.content_hash == second.content_hash


def test_robots_block_returns_reason_and_logs(monkeypatch):
    svc = service()
    monkeypatch.setattr(svc, "_robots_allowed", lambda *_: False)
    result = svc.fetch("https://example.com/private")
    assert result.reason == "blocked by robots.txt"
    assert svc.db.execute("SELECT error FROM tool_calls WHERE tool = 'fetch'").fetchone()[0] == result.reason


def test_retry_cap(monkeypatch):
    svc = service()
    attempts = []

    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs):
            attempts.append(1)
            raise httpx.ReadTimeout("offline")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: Client())
    try:
        svc._request("https://example.com")
    except RuntimeError as exc:
        assert "3 attempts" in str(exc)
    assert len(attempts) == 3


def test_stackexchange_uses_explicit_sites_and_warns_when_empty(monkeypatch, caplog):
    svc = service()
    monkeypatch.setattr(svc, "request_json", lambda *args, **kwargs: {"items": [{"link": "https://stackoverflow.com/q/1", "title": "Question", "body": "<p>Body</p>", "creation_date": 1790000000}], "quota_remaining": 99})
    assert connectors.stackexchange(svc, "monitoring", 3, ["stackoverflow"])[0].url.endswith("/q/1")
    with caplog.at_level("WARNING"):
        assert connectors.stackexchange(svc, "monitoring", 3, []) == []
    assert "no configured sites" in caplog.text


def test_stackexchange_unescapes_title(monkeypatch):
    svc = service()
    monkeypatch.setattr(svc, "request_json", lambda *args, **kwargs: {"items": [{"link": "https://stackoverflow.com/q/1", "title": "Can&#39;t monitor", "body": "<p>It&#39;s useful</p>", "creation_date": 1790000000}]})
    hit = connectors.stackexchange(svc, "monitoring", 3, ["stackoverflow"])[0]
    assert hit.title == "Can't monitor"
    assert hit.snippet == "It's useful"


def test_rss_uses_explicit_feeds_without_environment(monkeypatch):
    import pytest
    pytest.importorskip("feedparser")
    svc = service()
    monkeypatch.setattr(svc, "request_bytes", lambda url: b"<rss><channel><item><title>Monitoring</title><link>https://example.com/a</link><description>API monitoring</description></item></channel></rss>")
    monkeypatch.setitem(svc._connectors, "rss", lambda *_args, **_kwargs: connectors.rss(svc, "monitoring", 3, ["https://example.com/feed"]))
    assert svc.search("rss", "monitoring", 3, feeds=["https://example.com/feed"])[0].url == "https://example.com/a"


def test_google_news_feed_skips_keyword_filter(monkeypatch):
    pytest.importorskip("feedparser")
    svc = service()
    monkeypatch.setattr(svc, "request_bytes", lambda _: b"<rss><channel><item><title>Different title</title><link>https://news.google.com/rss/articles/x</link><description>Different text</description></item></channel></rss>")
    monkeypatch.setattr(svc, "resolve_url", lambda url: "https://example.com/article")
    monkeypatch.setattr(svc, "fetch", lambda url: Document(url, "example.com", "real article text", None, "hash", "2026-11-24T00:00:00+00:00", False, None, True))
    assert svc.search("rss", "term-not-present", 3, feeds=["https://news.google.com/rss/search?q=term"])[0].url == "https://example.com/article"


def test_ddg_snippet_is_capped(monkeypatch):
    import sys
    import types
    sys.modules["ddgs"] = types.SimpleNamespace(DDGS=lambda: types.SimpleNamespace(text=lambda *args, **kwargs: [{"href": "https://example.com", "title": "x", "body": "x" * 100}]))
    svc = service()
    svc.settings.retrieval_max_snippet_chars = 10
    assert len(connectors.ddg(svc, "query", 1)[0].snippet) == 10


def test_extracted_text_and_date_are_normalized_and_capped(monkeypatch):
    import sys
    import types
    sys.modules["trafilatura"] = types.SimpleNamespace(
        extract=lambda *args, **kwargs: "x" * 100,
        extract_metadata=lambda *args, **kwargs: types.SimpleNamespace(date="Sun, 01 Nov 2026 07:00:00 GMT"),
    )
    svc = service()
    svc.settings.retrieval_max_text_chars = 12
    text, published_at = svc._extract("https://example.com", b"<html></html>")
    assert len(text) == 12
    assert published_at == "2026-11-01T07:00:00+00:00"
