"""Small, database-backed retrieval layer used by pipeline modules."""

from .service import Document, RetrievalService, SearchHit, normalize_url

__all__ = ["Document", "RetrievalService", "SearchHit", "normalize_url"]
