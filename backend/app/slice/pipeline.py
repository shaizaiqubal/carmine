from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import numpy as np

from ..db import Database
from ..llm.client import AllProvidersFailed, LLMClient
from ..llm.embeddings import EmbeddingEngine
from ..llm.privacy import wrap_untrusted_content
from ..retrieval import RetrievalService, normalize_url
from ..retrieval.types import Document, SearchHit
from ..startup_config import feeds_for_profile, load_market_module
from .chunking import TextChunk, chunk_text, quote_in_passages
from .config import MARKET_MODULE, ModuleConfig
from .models import ExtractionOutput, ObjectionCandidate, QueryPlan

logger = logging.getLogger(__name__)


@dataclass
class RetrievedDoc:
    hit: SearchHit
    document: Document
    source_id: str


@dataclass
class SelectedPassage:
    chunk: TextChunk
    score: float


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_queries(values: list[str], cap: int) -> list[str]:
    result = []
    seen = set()
    for value in values:
        query = " ".join(value.split()).strip()
        key = query.casefold()
        if query and key not in seen and len(query.split()) <= 8 and not query.casefold().startswith(("http://", "https://")):
            result.append(query)
            seen.add(key)
        if len(result) >= cap:
            break
    return result


def _iso_sort_value(value: str | None) -> str:
    return value or ""


def _source_id(db: Database, url: str) -> str | None:
    row = db.execute("SELECT id FROM sources WHERE normalized_url = ? ORDER BY fetched_at DESC LIMIT 1", (normalize_url(url),)).fetchone()
    return row[0] if row else None


def _dict_rows(cursor) -> list[dict[str, Any]]:
    names = [column[0] for column in (cursor.description or [])]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _already_extracted(db: Database, assumption_id: str, content_hash: str) -> bool:
    return db.execute("SELECT 1 FROM objection_candidates c JOIN sources s ON s.id = c.source_id WHERE c.assumption_id = ? AND s.content_hash = ? LIMIT 1", (assumption_id, content_hash)).fetchone() is not None


class SlicePipeline:
    def __init__(self, db: Database, llm: LLMClient | None = None, retrieval: RetrievalService | None = None, embeddings: EmbeddingEngine | None = None, module: ModuleConfig = MARKET_MODULE):
        self.db = db
        self.module = module
        self.llm = llm or LLMClient(db)
        self.retrieval = retrieval or RetrievalService(db)
        self.embeddings = embeddings or EmbeddingEngine(db)

    def run(self, startup_id: str, *, assumption_index: int | None = None, stage: str = "extract", force: bool = False, run_id: str | None = None) -> dict[str, Any]:
        if stage not in {"plan", "retrieve", "select", "extract"}:
            raise ValueError("stage must be plan, retrieve, select, or extract")
        startup = self.db.execute("SELECT name, profile_json FROM startups WHERE id = ?", (startup_id,)).fetchone()
        if not startup:
            raise ValueError(f"startup not found: {startup_id}")
        profile = json.loads(startup[1])
        market_config = load_market_module(profile)
        rows = self.db.execute("SELECT id, text FROM assumptions WHERE startup_id = ? AND status = 'confirmed' ORDER BY created_at, id", (startup_id,)).fetchall()
        if assumption_index is not None:
            if assumption_index < 0 or assumption_index >= len(rows):
                raise ValueError("assumption index is outside the confirmed assumptions")
            rows = [rows[assumption_index]]
        if not rows:
            raise ValueError("no confirmed assumptions")
        run_id = run_id or str(uuid.uuid4())
        self.db.execute("INSERT INTO runs (id, startup_id, started_at, new_sources, new_objections) VALUES (?, ?, ?, 0, 0)", (run_id, startup_id, _now()))
        self.db.commit()
        plans: dict[str, QueryPlan] = {}
        retrieved: dict[str, list[RetrievedDoc]] = {}
        selected: dict[str, dict[str, list[SelectedPassage]]] = {}
        summary = {"run_id": run_id, "startup_id": startup_id, "module": self.module.name, "queries_planned": 0, "hits_per_connector": {}, "docs_fetched": 0, "docs_dropped_at_selection": 0, "passages_sent": 0, "extraction_calls": 0, "candidates": 0, "candidates_quote_in_passage_false": 0, "low_evidence_assumptions": [], "llm_calls": 0, "tokens_in": 0, "tokens_out": 0}
        try:
            for assumption_id, assumption_text in rows:
                plan = self._plan(profile, assumption_id, assumption_text, startup_id, run_id)
                if plan is None:
                    continue
                plans[assumption_id] = plan
                summary["queries_planned"] += sum(len(getattr(plan, connector)) for connector in self.module.connectors)
            if stage == "plan":
                return self._finish(run_id, summary, plans, retrieved, selected)
            feeds = feeds_for_profile(profile, market_config)
            for assumption_id, plan in plans.items():
                docs, hits = self._retrieve(assumption_id, plan, startup_id, run_id, market_config.se_sites, feeds, force)
                retrieved[assumption_id] = docs
                for connector, count in hits.items(): summary["hits_per_connector"][connector] = summary["hits_per_connector"].get(connector, 0) + count
                summary["docs_fetched"] += len(docs)
            if stage == "retrieve":
                return self._finish(run_id, summary, plans, retrieved, selected)
            for assumption_id, docs in retrieved.items():
                assumption_text = next(row[1] for row in rows if row[0] == assumption_id)
                selected[assumption_id], dropped = self._select(assumption_text, docs, plans[assumption_id])
                summary["docs_dropped_at_selection"] += dropped
                summary["passages_sent"] += sum(len(passages) for passages in selected[assumption_id].values())
            if stage == "select":
                return self._finish(run_id, summary, plans, retrieved, selected)
            for assumption_id, docs in retrieved.items():
                candidates = self._extract(assumption_id, rows, docs, selected[assumption_id], profile, startup_id, run_id, summary)
                summary["candidates"] += candidates
                if candidates == 0:
                    self._record_low_evidence(run_id, startup_id, assumption_id, sum(len(getattr(plans[assumption_id], c)) for c in self.module.connectors), len(docs), sum(len(v) for v in selected[assumption_id].values()))
                    summary["low_evidence_assumptions"].append(assumption_id)
            return self._finish(run_id, summary, plans, retrieved, selected)
        except Exception:
            self._finish(run_id, summary, plans, retrieved, selected, failed=True)
            raise

    def _plan(self, profile: dict[str, Any], assumption_id: str, assumption: str, startup_id: str, run_id: str) -> QueryPlan | None:
        module_details = {"name": self.module.name, "connectors": self.module.connectors, "caps": {"max_queries_per_connector": self.module.max_queries_per_connector, "max_docs_per_assumption": self.module.max_docs_per_assumption}, "severity_rubric": self.module.severity_rubric}
        prompt = self.module.query_planning_prompt + "\nModule config:\n" + json.dumps(module_details, sort_keys=True) + "\nAvailable connectors: " + ", ".join(self.module.connectors) + "\nStartup profile:\n" + wrap_untrusted_content(json.dumps(profile, sort_keys=True), "startup profile") + "\nAssumption (design disconfirming searches):\n" + wrap_untrusted_content(assumption, "assumption")
        error = None
        for attempt in range(2):
            try:
                result = self.llm.complete("query_plan", [{"role": "system", "content": prompt}], QueryPlan, startup_id=startup_id, run_id=run_id)
                raw = result.value
                return QueryPlan(**{connector: _dedupe_queries(getattr(raw, connector), self.module.max_queries_per_connector) for connector in self.module.connectors})
            except ValueError as exc:
                error = exc
                if attempt == 0:
                    continue
                break
            except (AllProvidersFailed, TypeError) as exc:
                error = exc
                break
        logger.error("query planning skipped assumption=%s: %s", assumption_id, error)
        return None

    def _retrieve(self, assumption_id: str, plan: QueryPlan, startup_id: str, run_id: str, sites: list[str], feeds: list[str], force: bool) -> tuple[list[RetrievedDoc], dict[str, int]]:
        hits: list[SearchHit] = []
        counts = {}
        for connector in self.module.connectors:
            connector_hits = []
            if connector == "rss":
                general_feeds, google_feeds = feeds[:-1], feeds[-1:]
                for query in getattr(plan, connector):
                    connector_hits.extend(self.retrieval.search(connector, query, self.module.max_docs_per_assumption, run_id=run_id, sites=sites, feeds=general_feeds))
                if google_feeds:
                    connector_hits.extend(self.retrieval.search(connector, "", self.module.max_docs_per_assumption, run_id=run_id, sites=sites, feeds=google_feeds))
            else:
                for query in getattr(plan, connector):
                    connector_hits.extend(self.retrieval.search(connector, query, self.module.max_docs_per_assumption, run_id=run_id, sites=sites, feeds=feeds))
            counts[connector] = len(connector_hits)
            hits.extend(connector_hits)
        unique: dict[str, SearchHit] = {}
        for hit in hits:
            unique.setdefault(normalize_url(hit.url), hit)
        ordered = sorted(unique.values(), key=lambda hit: (_iso_sort_value(hit.published_at), urlparse(hit.url).netloc), reverse=True)
        chosen: list[SearchHit] = []
        domains: set[str] = set()
        for hit in ordered:
            if len(chosen) >= self.module.max_docs_per_assumption:
                break
            domain = urlparse(normalize_url(hit.url)).netloc
            if domain not in domains:
                chosen.append(hit); domains.add(domain)
        for hit in ordered:
            if len(chosen) >= self.module.max_docs_per_assumption:
                break
            if hit not in chosen:
                chosen.append(hit)
        docs = []
        for hit in chosen:
            document = self.retrieval.fetch(hit.url, run_id=run_id)
            if document.reason or not document.text:
                continue
            if not force and _already_extracted(self.db, assumption_id, document.content_hash):
                continue
            source_id = _source_id(self.db, document.url)
            if source_id:
                docs.append(RetrievedDoc(hit, document, source_id))
        return docs, counts

    def _select(self, assumption_text: str, docs: list[RetrievedDoc], plan: QueryPlan) -> tuple[dict[str, list[SelectedPassage]], int]:
        result = {}
        dropped = 0
        query_texts = [" ".join(getattr(plan, connector)) for connector in self.module.connectors]
        query_texts = [text for text in query_texts if text]
        for item in docs:
            chunks = chunk_text(item.document.text)
            if not chunks:
                dropped += 1; continue
            chunk_vectors = self.embeddings.embed([chunk.text for chunk in chunks], chunk_indices=[chunk.index for chunk in chunks]).vectors
            query_vectors = self.embeddings.embed([self.module.embedding_query_prefix + assumption_text] + [self.module.embedding_query_prefix + text for text in query_texts], chunk_indices=[-1] + list(range(-2, -2 - len(query_texts), -1))).vectors
            matrix = np.asarray(chunk_vectors, dtype=float)
            queries = np.asarray(query_vectors, dtype=float)
            matrix = matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
            queries = queries / np.maximum(np.linalg.norm(queries, axis=1, keepdims=True), 1e-12)
            scores = np.max(matrix @ queries.T, axis=1)
            selected = [SelectedPassage(chunk, float(score)) for chunk, score in sorted(zip(chunks, scores), key=lambda pair: float(pair[1]), reverse=True) if score >= self.module.min_similarity][:self.module.passages_per_doc]
            if selected:
                result[item.source_id] = selected
            else:
                dropped += 1
        logger.info("passage selection dropped_docs=%s selected_docs=%s", dropped, len(result))
        return result, dropped

    def _extract(self, assumption_id: str, rows, docs: list[RetrievedDoc], selected: dict[str, list[SelectedPassage]], profile: dict[str, Any], startup_id: str, run_id: str, summary: dict[str, Any]) -> int:
        assumption = next(row[1] for row in rows if row[0] == assumption_id)
        total = 0
        for item in docs:
            passages = selected.get(item.source_id, [])[:self.module.max_passages_per_extraction_call]
            if not passages:
                continue
            passage_text = "\n\n".join(f"[passage_id=p{index + 1}, chars {passage.chunk.start}-{passage.chunk.end}]\n{passage.chunk.text}" for index, passage in enumerate(passages))
            prompt = self.module.extraction_prompt + "\nSeverity rubric:\n" + json.dumps(self.module.severity_rubric, sort_keys=True) + "\nAssumption:\n" + wrap_untrusted_content(assumption, "assumption") + f"\nPublished date: {item.document.published_at}\nPassages:\n" + wrap_untrusted_content(passage_text, "retrieved passages") + "\nReturn a JSON array of objects with text, quote, passage_id, assumption_id, severity, confidence."
            summary["extraction_calls"] += 1
            result = None
            error = None
            for attempt in range(2):
                try:
                    result = self.llm.complete("extract", [{"role": "system", "content": prompt}], ExtractionOutput, startup_id=startup_id, run_id=run_id)
                    break
                except ValueError as exc:
                    error = exc
                    if attempt == 0:
                        continue
                except (AllProvidersFailed, TypeError) as exc:
                    error = exc
                break
            if result is None:
                logger.error("extraction skipped assumption=%s source=%s: %s", assumption_id, item.document.url, error)
                continue
            candidates = result.value.root
            for candidate in candidates:
                passage_number = int(candidate.passage_id[1:])
                if passage_number < 1 or passage_number > len(passages):
                    logger.error("dropping candidate with invalid passage_id=%s source=%s", candidate.passage_id, item.document.url)
                    continue
                selected_passage = passages[passage_number - 1]
                quote_ok = quote_in_passages(candidate.quote, [selected_passage.chunk.text])
                fetched_urls = {doc.document.url for doc in docs}
                if item.document.url not in fetched_urls:
                    logger.error("dropping candidate with source outside fetched documents: %s", item.document.url)
                    continue
                raw = candidate.model_dump()
                raw["source_url_resolved_by_pipeline"] = item.document.url
                self.db.execute("INSERT INTO objection_candidates (id, run_id, startup_id, assumption_id, module, source_id, text, quote, source_url, severity, confidence_raw, quote_in_passage, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), run_id, startup_id, assumption_id, self.module.name, item.source_id, candidate.text, candidate.quote, item.document.url, candidate.severity, candidate.confidence, int(quote_ok), json.dumps(raw)))
                total += 1
                summary["candidates_quote_in_passage_false"] += int(not quote_ok)
        self.db.commit()
        return total

    def _record_low_evidence(self, run_id: str, startup_id: str, assumption_id: str, queries: int, docs: int, passages: int):
        self.db.execute("INSERT INTO low_evidence_results (id, run_id, startup_id, assumption_id, module, queries_planned, docs_fetched, passages_sent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), run_id, startup_id, assumption_id, self.module.name, queries, docs, passages))
        self.db.commit()

    def _finish(self, run_id: str, summary: dict[str, Any], plans, retrieved, selected, failed: bool = False) -> dict[str, Any]:
        summary["status"] = "failed" if failed else "finished"
        summary["llm_calls"] = self.db.execute("SELECT COUNT(*) FROM llm_calls WHERE run_id = ?", (run_id,)).fetchone()[0]
        tokens = self.db.execute("SELECT COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0) FROM llm_calls WHERE run_id = ?", (run_id,)).fetchone()
        summary["tokens_in"], summary["tokens_out"] = tokens[0], tokens[1]
        self.db.execute("UPDATE runs SET finished_at = ?, new_sources = ?, new_objections = ? WHERE id = ?", (_now(), summary["docs_fetched"], summary["candidates"], run_id)); self.db.commit()
        candidates = _dict_rows(self.db.execute("SELECT id, assumption_id, source_id, text, quote, source_url, severity, confidence_raw, quote_in_passage, created_at FROM objection_candidates WHERE run_id = ? ORDER BY created_at, id", (run_id,)))
        low_evidence = _dict_rows(self.db.execute("SELECT id, assumption_id, queries_planned, docs_fetched, passages_sent, created_at FROM low_evidence_results WHERE run_id = ? ORDER BY created_at, id", (run_id,)))
        return {"summary": summary, "plans": {key: value.model_dump() for key, value in plans.items()}, "retrieved": {key: [{"url": doc.document.url, "domain": doc.document.domain, "content_hash": doc.document.content_hash, "published_at": doc.document.published_at, "text_chars": len(doc.document.text), "source_id": doc.source_id} for doc in values] for key, values in retrieved.items()}, "selected": {key: {source: [{"text": passage.chunk.text, "start": passage.chunk.start, "end": passage.chunk.end, "score": passage.score} for passage in values] for source, values in passages.items()} for key, passages in selected.items()}, "candidates": candidates, "low_evidence": low_evidence}


def run_slice(db: Database, startup_id: str, **kwargs) -> dict[str, Any]:
    return SlicePipeline(db).run(startup_id, **kwargs)
