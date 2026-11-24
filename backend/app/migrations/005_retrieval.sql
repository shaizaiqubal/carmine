ALTER TABLE sources ADD COLUMN normalized_url TEXT;
ALTER TABLE sources ADD COLUMN text TEXT;
ALTER TABLE sources ADD COLUMN fetch_error TEXT;

CREATE INDEX IF NOT EXISTS idx_sources_normalized_url
  ON sources(normalized_url, fetched_at);

CREATE TABLE IF NOT EXISTS retrieval_search_cache (
  id TEXT PRIMARY KEY,
  cache_key TEXT NOT NULL,
  connector TEXT NOT NULL,
  query TEXT NOT NULL,
  results_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_retrieval_search_cache_lookup
  ON retrieval_search_cache(cache_key, expires_at);

CREATE TABLE IF NOT EXISTS retrieval_robots_cache (
  domain TEXT PRIMARY KEY,
  robots_text TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
