CREATE TABLE IF NOT EXISTS llm_cache (
  id TEXT PRIMARY KEY,
  cache_key TEXT NOT NULL,
  startup_id TEXT REFERENCES startups(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  temperature REAL NOT NULL,
  response_text TEXT NOT NULL,
  tokens_in INTEGER,
  tokens_out INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_cache_lookup
  ON llm_cache(cache_key, startup_id, expires_at);
CREATE TABLE IF NOT EXISTS embeddings (
  id TEXT PRIMARY KEY,
  startup_id TEXT REFERENCES startups(id) ON DELETE CASCADE,
  content_hash TEXT NOT NULL,
  model TEXT NOT NULL,
  revision TEXT NOT NULL,
  dim INTEGER NOT NULL,
  vector_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_embeddings_identity
  ON embeddings(content_hash, model, revision, dim, startup_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_lookup
  ON embeddings(content_hash, model, revision, dim, startup_id);
