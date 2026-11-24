"""Opt-in live retrieval smoke test: python scripts/retrieval_smoke.py -m live"""
import argparse
import os
import sys

from app.config import Settings
from app.db import Database, apply_migrations
from app.retrieval import RetrievalService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", choices=["live"], required=True)
    parser.add_argument("--query", default="api monitoring tool")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    settings = Settings()
    # Optional developer-only overrides. Pipeline code must pass startup config explicitly.
    sites = [item.strip() for item in os.getenv("STACKEXCHANGE_SITES", "").split(",") if item.strip()]
    feeds = [item.strip() for item in os.getenv("RSS_FEED_URLS", "").split(",") if item.strip()]
    db = Database(settings)
    apply_migrations(db, __import__("pathlib").Path(__file__).parents[1] / "app" / "migrations")
    service = RetrievalService(db, settings)
    try:
        for connector in ("hn", "stackexchange", "rss", "ddg"):
            hits = service.search(connector, args.query, args.limit, sites=sites, feeds=feeds)
            print(f"{connector}: {len(hits)} results")
            for index, hit in enumerate(hits, 1):
                print(f"  {index}. {hit.title or '(untitled)'} | {hit.url} | published_at={hit.published_at}")
        for connector in ("hn", "ddg"):
            hits = service.search(connector, args.query, 1, sites=sites, feeds=feeds)
            if hits:
                document = service.fetch(hits[0].url)
                print(f"fetch {connector}: {len(document.text)} chars, published_at={document.published_at}, reason={document.reason}")
            else:
                print(f"fetch {connector}: skipped (no result)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
