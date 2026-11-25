from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from typing import TYPE_CHECKING

from .types import Document, SearchHit

if TYPE_CHECKING:
    from .service import RetrievalService

logger = logging.getLogger(__name__)


def hn(service: RetrievalService, query: str, limit: int) -> list[SearchHit]:
    data = service.request_json("https://hn.algolia.com/api/v1/search", {"query": query, "hitsPerPage": limit})
    result = []
    for item in data.get("hits", []):
        text = item.get("comment_text") or item.get("story_text") or ""
        title = item.get("title") or item.get("story_title") or ""
        url = item.get("url") or (f"https://news.ycombinator.com/item?id={item['objectID']}" if item.get("objectID") else "")
        if url:
            result.append(SearchHit(url, title, _strip_html(text), normalize_date(item.get("created_at")), "hn"))
    return result[:limit]


def stackexchange(service: RetrievalService, query: str, limit: int, sites: list[str] | tuple[str, ...] = ()) -> list[SearchHit]:
    if not sites:
        logger.warning("stackexchange connector has no configured sites")
        return []
    result = []
    for site in sites:
        params = {"q": query, "pagesize": limit, "site": site, "filter": "withbody"}
        if service.settings.stackexchange_key:
            params["key"] = service.settings.stackexchange_key
        try:
            data = service.request_json("https://api.stackexchange.com/2.3/search/advanced", params)
            if data.get("backoff"):
                service.sleep(float(data["backoff"]))
            logger.info("stackexchange quota_remaining=%s site=%s", data.get("quota_remaining"), site)
            for item in data.get("items", []):
                if item.get("link"):
                    body = _strip_html(item.get("body", ""))
                    result.append(SearchHit(item["link"], _strip_html(item.get("title", "")), body[:500], normalize_date(_iso_epoch(item.get("creation_date"))), "stackexchange"))
        except Exception as exc:
            logger.error("stackexchange search failed for %s: %s", site, exc)
            return []
    return result[:limit]


def rss(service: RetrievalService, query: str, limit: int, feeds: list[str] | tuple[str, ...] = ()) -> list[SearchHit]:
    import feedparser
    keywords = [word.casefold() for word in query.split() if word.strip()]
    result = []
    for feed_url in feeds:
        try:
            feed = feedparser.parse(service.request_bytes(feed_url))
            if getattr(feed, "bozo", False):
                logger.warning("rss feed was not cleanly parseable: %s", feed_url)
            if not feed.entries:
                logger.warning("rss feed returned no parseable items: %s", feed_url)
            for entry in feed.entries:
                content = " ".join(str(item.get("value", "")) for item in entry.get("content", []))
                tags = " ".join(str(item.get("term", "")) for item in entry.get("tags", []))
                haystack = " ".join(str(entry.get(field, "")) for field in ("title", "summary", "description", "subtitle", "author") )
                haystack = f"{haystack} {content} {tags}".casefold()
                # RSS feeds are not consistent about which fields carry article text;
                # match any query term rather than dropping otherwise relevant items.
                is_google_news = "news.google.com" in feed_url.casefold()
                if keywords and not is_google_news and not any(word in haystack for word in keywords):
                    continue
                if entry.get("link"):
                    summary = entry.get("summary") or entry.get("description") or content
                    link = entry["link"]
                    if "news.google.com" in link:
                        link = service.resolve_url(link)
                        if link == entry["link"]:
                            continue
                        # Google links can resolve to an interstitial; only return
                        # the hit when the resolved page has usable article text.
                        document = service.fetch(link)
                        if document.reason or not document.text.strip():
                            continue
                    result.append(SearchHit(link, entry.get("title", ""), _strip_html(summary)[:500], normalize_date(entry.get("published_parsed") or entry.get("updated_parsed") or entry.get("published") or entry.get("updated")), "rss"))
        except Exception as exc:
            logger.error("rss feed failed for %s: %s", feed_url, exc)
    return result[:limit]


def ddg(service: RetrievalService, query: str, limit: int) -> list[SearchHit]:
    from ddgs import DDGS
    last = None
    for attempt in range(service.settings.retrieval_max_retries + 1):
        try:
            rows = DDGS().text(query, max_results=limit)
            return [SearchHit(row["href"], row.get("title", ""), (row.get("body", "") or "")[:service.settings.retrieval_max_snippet_chars], None, "ddg") for row in rows if row.get("href")]
        except Exception as exc:
            last = exc
            if attempt < service.settings.retrieval_max_retries:
                service.sleep(min(8.0, 1.0 * (2 ** attempt)))
    logger.error("ddg search failed after retries: %s", last)
    return []


def direct_document(hit: SearchHit) -> Document:
    from urllib.parse import urlparse
    from .service import cleaned_hash
    text = _strip_html(hit.snippet)
    return Document(hit.url, urlparse(hit.url).netloc.lower(), text, hit.published_at, cleaned_hash(text), datetime.now(timezone.utc).isoformat(), False, None, True)


def _strip_html(value: str) -> str:
    from bs4 import BeautifulSoup
    return " ".join(BeautifulSoup(html.unescape(value or ""), "html.parser").get_text(" ").split())


def _iso_epoch(value: int | None) -> str | None:
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None


def normalize_date(value) -> str | None:
    if not value:
        return None
    if hasattr(value, "tm_year"):
        return datetime(*value[:6], tzinfo=timezone.utc).isoformat()
    if isinstance(value, datetime):
        date = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc).isoformat()
    text = str(value).strip()
    try:
        date = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc).isoformat()
