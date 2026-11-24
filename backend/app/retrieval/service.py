from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from urllib.parse import unquote

import httpx

from ..config import Settings
from ..db import Database
from .types import Document, SearchHit
from . import connectors

logger = logging.getLogger(__name__)
TRACKING_PARAMS = {"fbclid", "gclid", "dclid", "mc_cid", "mc_eid", "ref", "ref_", "source"}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.hostname.lower() if parsed.hostname else ""
    if parsed.port and not ((parsed.scheme == "http" and parsed.port == 80) or (parsed.scheme == "https" and parsed.port == 443)):
        host += f":{parsed.port}"
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if not (key.lower().startswith("utm_") or key.lower() in TRACKING_PARAMS)]
    return urlunparse((parsed.scheme.lower(), host, parsed.path or "/", "", urlencode(sorted(query)), ""))


def cleaned_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RetrievalService:
    def __init__(self, db: Database, settings: Settings | None = None, sleeper=time.sleep):
        self.db = db
        self.settings = settings or db.settings
        self.sleep = sleeper
        self._last_domain_request: dict[str, float] = {}
        self._connectors = {"hn": connectors.hn, "stackexchange": connectors.stackexchange, "rss": connectors.rss, "ddg": connectors.ddg}

    def search(self, connector: str, query: str, limit: int = 10, run_id: str | None = None, *, sites: list[str] | tuple[str, ...] = (), feeds: list[str] | tuple[str, ...] = ()) -> list[SearchHit]:
        started = time.monotonic(); cache_scope = "\0".join([connector, query.casefold(), ",".join(sites), ",".join(feeds)]); key = hashlib.sha256(cache_scope.encode()).hexdigest(); now = datetime.now(timezone.utc)
        row = self.db.execute("SELECT results_json FROM retrieval_search_cache WHERE cache_key = ? AND expires_at > ? ORDER BY created_at DESC LIMIT 1", (key, now.isoformat())).fetchone()
        if row:
            result = [SearchHit(**item) for item in json.loads(row[0])]
            self._log("search:" + connector, query, True, started, None, run_id)
            return result[:limit]
        error = None; result: list[SearchHit] = []
        try:
            if connector not in self._connectors:
                raise ValueError(f"unknown connector: {connector}")
            if connector == "stackexchange":
                result = connectors.stackexchange(self, query, limit, sites)
            elif connector == "rss":
                result = connectors.rss(self, query, limit, feeds)
            else:
                result = self._connectors[connector](self, query, limit)
            if connector in {"hn", "stackexchange"}:
                for hit in result:
                    if hit.snippet:
                        self._store_direct_hit(hit)
            expires = now + timedelta(seconds=self.settings.retrieval_search_cache_ttl_seconds)
            self.db.execute("INSERT INTO retrieval_search_cache (id, cache_key, connector, query, results_json, expires_at) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), key, connector, query, json.dumps([item.__dict__ for item in result]), expires.isoformat()))
            self.db.commit()
        except Exception as exc:
            error = str(exc); logger.error("search failed connector=%s query=%s: %s", connector, query, exc)
        self._log("search:" + connector, query, False, started, error, run_id)
        return result

    def _store_direct_hit(self, hit: SearchHit):
        normalized = normalize_url(hit.url); parsed = urlparse(normalized); text = hit.snippet.strip()
        if not text:
            return
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("INSERT INTO sources (id, url, normalized_url, domain, text, fetched_at, published_at, content_hash, fetch_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)", (str(uuid.uuid4()), normalized, normalized, parsed.netloc.lower(), text, now, hit.published_at, cleaned_hash(text)))
        self.db.commit()

    def fetch(self, url: str, run_id: str | None = None) -> Document:
        normalized = normalize_url(url); parsed = urlparse(normalized); domain = parsed.netloc.lower(); now = datetime.now(timezone.utc); started = time.monotonic()
        row = self.db.execute("SELECT url, domain, text, published_at, content_hash, fetched_at FROM sources WHERE normalized_url = ? AND text IS NOT NULL AND fetched_at > ? ORDER BY fetched_at DESC LIMIT 1", (normalized, (now - timedelta(seconds=self.settings.retrieval_fetch_cache_ttl_seconds)).isoformat())).fetchone()
        if row:
            document = Document(row[0], row[1] or domain, row[2], row[3], row[4] or cleaned_hash(row[2]), row[5], True, None, False)
            self._log("fetch", normalized, True, started, None, run_id); return document
        error = None
        try:
            if parsed.scheme not in {"http", "https"}:
                raise ValueError("unsupported URL scheme")
            if not self._robots_allowed(normalized, domain):
                raise ValueError("blocked by robots.txt")
            response = self._request(normalized)
            content_type = response.headers.get("content-type", "").lower()
            if content_type and "html" not in content_type and "xhtml" not in content_type:
                raise ValueError(f"non-HTML content type: {content_type}")
            if len(response.content) > self.settings.retrieval_max_response_bytes:
                raise ValueError("response exceeds maximum size")
            text, published_at = self._extract(normalized, response.content)
            if not text:
                raise ValueError("empty extracted text")
            digest = cleaned_hash(text)
            previous = self.db.execute("SELECT content_hash FROM sources WHERE normalized_url = ? ORDER BY fetched_at DESC LIMIT 1", (normalized,)).fetchone()
            is_new = not previous or previous[0] != digest
            fetched_at = now.isoformat()
            self.db.execute("INSERT INTO sources (id, url, normalized_url, domain, text, fetched_at, published_at, content_hash, fetch_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)", (str(uuid.uuid4()), normalized, normalized, domain, text, fetched_at, published_at, digest))
            self.db.commit()
            document = Document(normalized, domain, text, published_at, digest, fetched_at, False, None, is_new)
        except Exception as exc:
            error = str(exc); logger.error("fetch failed url=%s: %s", normalized, exc)
            self.db.execute("INSERT INTO sources (id, url, normalized_url, domain, fetched_at, fetch_error) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), normalized, normalized, domain, now.isoformat(), error)); self.db.commit()
            document = Document(normalized, domain, "", None, "", now.isoformat(), False, error, False)
        self._log("fetch", normalized, False, started, error, run_id); return document

    def request_json(self, url: str, params: dict) -> dict:
        return self._request(url, params=params).json()

    def request_bytes(self, url: str) -> bytes:
        return self._request(url).content

    def resolve_url(self, url: str) -> str:
        """Resolve redirect-wrapped links, retaining the original on failure."""
        try:
            response = self._request(url)
            final_url = str(response.url)
            if final_url and urlparse(final_url).netloc.lower() != "news.google.com":
                return final_url
            # Some Google News responses expose the target in canonical metadata.
            match = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:url|twitter:url)["\'][^>]+content=["\']([^"\']+)', response.text, re.I)
            resolved = unquote(match.group(1)) if match else url
            if urlparse(resolved).netloc.lower() == "news.google.com":
                raise ValueError("Google News link did not resolve to an article URL")
            return resolved
        except Exception as exc:
            logger.warning("could not resolve RSS URL %s: %s", url, exc)
            return url

    def _request(self, url: str, params: dict | None = None) -> httpx.Response:
        self._rate_limit(urlparse(url).netloc.lower()); last = None
        for attempt in range(self.settings.retrieval_max_retries + 1):
            try:
                with httpx.Client(timeout=self.settings.retrieval_http_timeout_seconds, follow_redirects=True, max_redirects=3, headers={"User-Agent": self.settings.retrieval_user_agent}) as client:
                    response = client.get(url, params=params)
                response.raise_for_status(); return response
            except (httpx.HTTPError, OSError) as exc:
                last = exc
                if attempt < self.settings.retrieval_max_retries:
                    self.sleep(min(8.0, 0.5 * (2 ** attempt)) + random.random() * 0.1)
        raise RuntimeError(f"request failed after {self.settings.retrieval_max_retries + 1} attempts: {last}")

    def _rate_limit(self, domain: str):
        wait = self.settings.retrieval_per_domain_delay_seconds - (time.monotonic() - self._last_domain_request.get(domain, 0))
        if wait > 0: self.sleep(wait)
        self._last_domain_request[domain] = time.monotonic()

    def _robots_allowed(self, url: str, domain: str) -> bool:
        now = datetime.now(timezone.utc); row = self.db.execute("SELECT robots_text FROM retrieval_robots_cache WHERE domain = ? AND expires_at > ?", (domain, now.isoformat())).fetchone()
        if row: text = row[0]
        else:
            try: text = self._request(f"{urlparse(url).scheme}://{domain}/robots.txt").text
            except Exception as exc: logger.warning("robots.txt unavailable for %s: %s", domain, exc); text = ""
            self.db.execute("INSERT OR REPLACE INTO retrieval_robots_cache (domain, robots_text, fetched_at, expires_at) VALUES (?, ?, ?, ?)", (domain, text, now.isoformat(), (now + timedelta(seconds=self.settings.retrieval_robots_cache_ttl_seconds)).isoformat())); self.db.commit()
        if not text: return True
        parser = RobotFileParser(); parser.parse(text.splitlines()); return parser.can_fetch(self.settings.retrieval_user_agent, url)

    def _extract(self, url: str, raw: bytes) -> tuple[str, str | None]:
        import trafilatura
        page = raw.decode("utf-8", errors="replace")
        if re.search(r"paywall|subscribe to continue|sign in to read", page, re.I) and len(page) < 100_000:
            raise ValueError("paywalled page")
        text = trafilatura.extract(page, url=url, include_comments=False, favor_precision=True) or ""
        from .connectors import normalize_date
        metadata = trafilatura.extract_metadata(page, default_url=url)
        text = text.strip()
        return text[: self.settings.retrieval_max_text_chars], normalize_date(getattr(metadata, "date", None) if metadata else None)

    def _log(self, tool: str, target: str, cache_hit: bool, started: float, error: str | None, run_id: str | None):
        self.db.execute("INSERT INTO tool_calls (id, run_id, tool, target, cache_hit, latency_ms, error) VALUES (?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), run_id, tool, target, int(cache_hit), int((time.monotonic() - started) * 1000), error)); self.db.commit()
