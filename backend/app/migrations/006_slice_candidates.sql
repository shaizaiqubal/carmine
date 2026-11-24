ALTER TABLE embeddings ADD COLUMN chunk_index INTEGER NOT NULL DEFAULT 0;
DROP INDEX IF EXISTS uq_embeddings_identity;
CREATE UNIQUE INDEX IF NOT EXISTS uq_embeddings_identity_chunk
  ON embeddings(content_hash, chunk_index, model, revision, dim, startup_id);

CREATE TABLE IF NOT EXISTS objection_candidates (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  startup_id TEXT NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
  assumption_id TEXT NOT NULL REFERENCES assumptions(id) ON DELETE CASCADE,
  module TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(id),
  text TEXT NOT NULL,
  quote TEXT NOT NULL,
  source_url TEXT NOT NULL,
  severity TEXT NOT NULL,
  confidence_raw REAL,
  quote_in_passage INTEGER NOT NULL,
  raw TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_objection_candidates_assumption_hash
  ON objection_candidates(assumption_id, source_id);

CREATE TABLE IF NOT EXISTS low_evidence_results (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  startup_id TEXT NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
  assumption_id TEXT NOT NULL REFERENCES assumptions(id) ON DELETE CASCADE,
  module TEXT NOT NULL,
  queries_planned INTEGER NOT NULL,
  docs_fetched INTEGER NOT NULL,
  passages_sent INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
