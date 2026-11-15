CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT,
  role TEXT NOT NULL DEFAULT 'founder' CHECK (role IN ('founder', 'team')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS startups (
  id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  profile_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS assumptions (
  id TEXT PRIMARY KEY,
  startup_id TEXT NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  category TEXT,
  status TEXT NOT NULL DEFAULT 'proposed',
  confirmed_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, url TEXT NOT NULL, domain TEXT, fetched_at TEXT,
  published_at TEXT, content_hash TEXT, text_path TEXT
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
  quote TEXT NOT NULL, quote_verified INTEGER NOT NULL DEFAULT 0,
  support_score REAL, support_model TEXT, recency_ok INTEGER
);
CREATE TABLE IF NOT EXISTS objections (
  id TEXT PRIMARY KEY, startup_id TEXT NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
  assumption_id TEXT REFERENCES assumptions(id) ON DELETE SET NULL,
  module TEXT NOT NULL, text TEXT NOT NULL, severity TEXT NOT NULL,
  confidence REAL, status TEXT NOT NULL DEFAULT 'new', first_seen_run TEXT,
  last_seen_run TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS objection_evidence (
  objection_id TEXT NOT NULL REFERENCES objections(id) ON DELETE CASCADE,
  evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  PRIMARY KEY (objection_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS verdicts (
  id TEXT PRIMARY KEY, objection_id TEXT NOT NULL REFERENCES objections(id) ON DELETE CASCADE,
  verdict TEXT NOT NULL, reason TEXT, response_plan TEXT, time_spent_ms INTEGER,
  decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS counter_arguments (
  id TEXT PRIMARY KEY, verdict_id TEXT NOT NULL REFERENCES verdicts(id) ON DELETE CASCADE,
  text TEXT NOT NULL, new_evidence_ids TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS validation_tasks (
  id TEXT PRIMARY KEY, objection_id TEXT NOT NULL REFERENCES objections(id) ON DELETE CASCADE,
  description TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, startup_id TEXT NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
  started_at TEXT, finished_at TEXT, new_sources INTEGER, new_objections INTEGER
);
CREATE TABLE IF NOT EXISTS llm_calls (
  id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id), provider TEXT, model TEXT,
  purpose TEXT, tokens_in INTEGER, tokens_out INTEGER, cache_hit INTEGER,
  latency_ms INTEGER, error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tool_calls (
  id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id), tool TEXT, target TEXT,
  cache_hit INTEGER, latency_ms INTEGER, error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), started_at TEXT,
  ended_at TEXT, active_ms INTEGER
);
CREATE TABLE IF NOT EXISTS ui_events (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), event TEXT NOT NULL,
  objection_id TEXT REFERENCES objections(id), ts_ms INTEGER NOT NULL
);
