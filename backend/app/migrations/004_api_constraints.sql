CREATE UNIQUE INDEX IF NOT EXISTS uq_counter_arguments_verdict
  ON counter_arguments(verdict_id);

CREATE INDEX IF NOT EXISTS idx_runs_startup_started
  ON runs(startup_id, started_at);
