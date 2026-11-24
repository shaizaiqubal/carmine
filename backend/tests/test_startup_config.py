import json
from pathlib import Path

import pytest

from app.config import Settings
from app.db import Database, apply_migrations
from app.startup_config import MarketModuleConfig, feeds_for_profile, google_news_search_feed, load_market_module, load_startup_seed


def test_market_config_validates_and_rejects_bad_feed():
    assert MarketModuleConfig(se_sites=["stackoverflow"], rss_feeds=["https://example.com/feed"]).se_sites == ["stackoverflow"]
    with pytest.raises(ValueError):
        MarketModuleConfig(rss_feeds=["file:///tmp/feed"])


def test_google_news_feed_is_encoded_and_has_no_literal_commas():
    url = google_news_search_feed(["API monitoring", "status, pages"], ["Better Stack"])
    assert url.startswith("https://news.google.com/rss/search?")
    assert "q=API+monitoring+status+pages+Better+Stack" in url
    assert "," not in url


def test_profile_loader_and_generated_feed():
    profile = {"keywords": ["API monitoring"], "competitors": ["Better Stack"], "market_module": {"se_sites": [], "rss_feeds": []}}
    config = load_market_module(json.dumps(profile))
    assert config.se_sites == []
    assert len(feeds_for_profile(profile, config)) == 1


def test_seed_loader_creates_startup_and_assumptions(tmp_path):
    path = tmp_path / "seed.yaml"
    path.write_text("""name: Example\nprofile:\n  keywords: [monitoring]\nassumptions:\n  - text: Customers pay\n    category: demand\nmarket_module:\n  se_sites: [stackoverflow]\n  rss_feeds: [https://example.com/feed]\n""")
    settings = Settings(database_path=":memory:", turso_database_url="", turso_auth_token="")
    db = Database(settings)
    apply_migrations(db, Path(__file__).parents[1] / "app" / "migrations")
    db.execute("INSERT INTO users (id) VALUES (?)", ("owner",))
    db.commit()
    startup_id = load_startup_seed(path, db, "owner")
    row = db.execute("SELECT name, profile_json FROM startups WHERE id = ?", (startup_id,)).fetchone()
    assert row[0] == "Example"
    assert load_market_module(row[1]).se_sites == ["stackoverflow"]
    assert db.execute("SELECT COUNT(*) FROM assumptions WHERE startup_id = ?", (startup_id,)).fetchone()[0] == 1
