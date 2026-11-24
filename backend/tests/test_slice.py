import json
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.db import Database, apply_migrations
from app.llm.configuration import LLMConfig
from app.llm.embeddings import EmbeddingEngine
from app.retrieval.types import Document, SearchHit
from app.slice.chunking import chunk_text, quote_in_passages
from app.slice.models import ExtractionOutput, ObjectionCandidate, QueryPlan
from app.slice.pipeline import SlicePipeline


def make_db():
    settings = Settings(database_path=":memory:", turso_database_url="", turso_auth_token="", retrieval_per_domain_delay_seconds=0)
    db = Database(settings)
    apply_migrations(db, Path(__file__).parents[1] / "app" / "migrations")
    db.execute("INSERT INTO users (id) VALUES ('slice-test')")
    db.execute("INSERT INTO startups (id, owner_user_id, name, profile_json) VALUES ('startup', 'slice-test', 'Test', ?)", (json.dumps({"keywords": ["API monitoring"], "competitors": ["Competitor"], "market_module": {"se_sites": [], "rss_feeds": []}}),))
    db.execute("INSERT INTO assumptions (id, startup_id, text, status, confirmed_at) VALUES ('assumption', 'startup', 'Teams will pay for API monitoring', 'confirmed', '2026-01-01T00:00:00+00:00')")
    db.commit()
    return db


def test_chunk_offsets_and_sentence_boundaries():
    text = " ".join(f"Sentence {index} explains a useful fact." for index in range(1, 90))
    chunks = chunk_text(text, min_words=30, max_words=45, overlap_words=5)
    assert chunks
    for chunk in chunks:
        assert text[chunk.start:chunk.end] == chunk.text
        assert chunk.text.strip().endswith(".")


def test_quote_matching_normalizes_whitespace_but_not_fabrication():
    assert quote_in_passages("exact   quoted text", ["This is exact quoted\ntext here."])
    assert not quote_in_passages("fabricated quote", ["This is the actual passage."])


def test_planner_retries_invalid_value_and_enforces_caps():
    db = make_db()

    class RetryPlanner:
        calls = 0

        def complete(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("invalid_json")
            return SimpleNamespace(value=QueryPlan(hn=["same", "same", "two words", "three words", "four words"], stackexchange=[], ddg=[], rss=[]))

    planner = RetryPlanner()
    pipeline = SlicePipeline(db, llm=planner)
    plan = pipeline._plan({}, "assumption", "Teams pay", "startup", "run")
    assert planner.calls == 2
    assert plan.hn == ["same", "two words", "three words"]


class FakeEmbeddingModel:
    def __init__(self):
        self.calls = 0

    def encode(self, texts, **kwargs):
        self.calls += 1
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeLLM:
    def __init__(self, extraction=None):
        self.extraction = extraction
        self.calls = []

    def complete(self, purpose, messages, schema, **kwargs):
        self.calls.append((purpose, schema))
        if purpose == "query_plan":
            return SimpleNamespace(value=QueryPlan(hn=["API monitoring complaints", "API monitoring complaints", "x " * 9], stackexchange=[], ddg=["API monitoring not worth it"], rss=[]))
        return SimpleNamespace(value=ExtractionOutput(self.extraction or []))


class FakeRetrieval:
    def __init__(self, db, text):
        self.db = db
        self.text = text

    def search(self, connector, query, limit, **kwargs):
        return [SearchHit("https://example.com/article", "Article", "snippet", "2026-01-01T00:00:00+00:00", connector)] if connector == "ddg" else []

    def fetch(self, url, **kwargs):
        content_hash = "hash-article"
        self.db.execute("INSERT OR REPLACE INTO sources (id, url, normalized_url, domain, text, fetched_at, content_hash) VALUES ('source', ?, ?, 'example.com', ?, '2026-01-01T00:00:00+00:00', ?)", (url, url, self.text, content_hash))
        self.db.commit()
        return Document(url, "example.com", self.text, "2026-01-01T00:00:00+00:00", content_hash, "2026-01-01T00:00:00+00:00", False, None, True)


def test_pipeline_caps_and_stores_unverified_candidate():
    db = make_db()
    settings = LLMConfig.load()
    config = settings
    text = " ".join(f"This passage says customers complain about the product and use a free alternative {i}." for i in range(70))
    llm = FakeLLM([ObjectionCandidate(text="The market has a free alternative", quote="customers complain about the product", source_url="https://example.com/article", assumption_id="assumption", severity="high", confidence=0.7)])
    embedding_config = __import__("dataclasses").replace(settings, embedding_dim=3, embedding_model="fake", embedding_revision="test")
    model = FakeEmbeddingModel()
    pipeline = SlicePipeline(db, llm=llm, retrieval=FakeRetrieval(db, text), embeddings=EmbeddingEngine(db, embedding_config, model=model))
    result = pipeline.run("startup")
    assert result["summary"]["candidates"] == 1
    row = db.execute("SELECT quote_in_passage, severity FROM objection_candidates").fetchone()
    assert row[0] == 1 and row[1] == "high"
    assert model.calls == 2


def test_embedding_cache_reuses_same_chunk_vectors():
    db = make_db()
    config = __import__("dataclasses").replace(LLMConfig.load(), embedding_dim=3, embedding_model="fake", embedding_revision="test")
    model = FakeEmbeddingModel()
    engine = EmbeddingEngine(db, config, model=model)
    engine.embed(["same chunk"], chunk_indices=[4])
    second = engine.embed(["same chunk"], chunk_indices=[4])
    assert second.cache_hits == [True]
    assert model.calls == 1


def test_low_evidence_record_is_written():
    db = make_db()
    pipeline = SlicePipeline(db, llm=FakeLLM([]), retrieval=FakeRetrieval(db, ""), embeddings=EmbeddingEngine(db, __import__("dataclasses").replace(LLMConfig.load(), embedding_dim=3), model=FakeEmbeddingModel()))
    result = pipeline.run("startup")
    assert result["summary"]["low_evidence_assumptions"] == ["assumption"]
    assert db.execute("SELECT COUNT(*) FROM low_evidence_results").fetchone()[0] == 1
