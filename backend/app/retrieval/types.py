from dataclasses import dataclass


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    snippet: str
    published_at: str | None
    connector: str


@dataclass(frozen=True)
class Document:
    url: str
    domain: str
    text: str
    published_at: str | None
    content_hash: str
    fetched_at: str
    from_cache: bool
    reason: str | None = None
    is_new: bool = False
