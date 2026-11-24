"""Typed per-startup retrieval configuration and seed loading."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal

from .db import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MarketModuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    se_sites: list[str] = Field(default_factory=list)
    rss_feeds: list[str] = Field(default_factory=list)

    @field_validator("se_sites", "rss_feeds")
    @classmethod
    def clean_values(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("connector values must be unique")
        return cleaned

    @field_validator("rss_feeds")
    @classmethod
    def validate_feeds(cls, values: list[str]) -> list[str]:
        for value in values:
            if not re.match(r"^https?://", value, re.IGNORECASE):
                raise ValueError(f"RSS feed must be an HTTP(S) URL: {value}")
        return values

    @field_validator("se_sites")
    @classmethod
    def validate_sites(cls, values: list[str]) -> list[str]:
        for value in values:
            if not re.match(r"^[a-z0-9][a-z0-9-]*$", value, re.IGNORECASE):
                raise ValueError(f"invalid Stack Exchange site: {value}")
        return values


class SeedAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    category: str | None = None
    status: Literal["proposed", "confirmed"] = "confirmed"


class StartupSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    profile: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[SeedAssumption] = Field(default_factory=list)
    market_module: MarketModuleConfig = Field(default_factory=MarketModuleConfig)

    @field_validator("assumptions", mode="before")
    @classmethod
    def normalize_assumptions(cls, values):
        return [{"text": value} if isinstance(value, str) else value for value in (values or [])]


def load_market_module(profile_json: str | dict[str, Any]) -> MarketModuleConfig:
    profile = json.loads(profile_json) if isinstance(profile_json, str) else profile_json
    return MarketModuleConfig.model_validate(profile.get("market_module", {}))


def search_terms(profile: dict[str, Any]) -> list[str]:
    values = profile.get("keywords", []) + profile.get("competitor_names", profile.get("competitors", []))
    return [value.strip() for value in values if isinstance(value, str) and value.strip()]


def google_news_search_feed(keywords: list[str], competitor_names: list[str]) -> str:
    terms = [re.sub(r"[\s,]+", " ", value).strip() for value in [*keywords, *competitor_names] if isinstance(value, str) and value.strip()]
    if not terms:
        raise ValueError("at least one keyword or competitor name is required")
    return "https://news.google.com/rss/search?" + urlencode({"q": " ".join(terms)}, safe="")


def feeds_for_profile(profile: dict[str, Any], config: MarketModuleConfig) -> list[str]:
    generated = google_news_search_feed(profile.get("keywords", []), profile.get("competitor_names", profile.get("competitors", [])))
    return [*config.rss_feeds, generated]


def load_startup_seed(path: str | Path, db: Database, owner_user_id: str) -> str:
    seed = StartupSeed.model_validate(yaml.safe_load(Path(path).read_text()))
    startup_id = str(uuid.uuid4())
    profile = dict(seed.profile)
    profile["market_module"] = seed.market_module.model_dump()
    db.execute("INSERT INTO startups (id, owner_user_id, name, profile_json) VALUES (?, ?, ?, ?)", (startup_id, owner_user_id, seed.name, json.dumps(profile)))
    for assumption in seed.assumptions:
        db.execute("INSERT INTO assumptions (id, startup_id, text, category, status, confirmed_at) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), startup_id, assumption.text, assumption.category, assumption.status, _now() if assumption.status == "confirmed" else None))
    db.commit()
    return startup_id
