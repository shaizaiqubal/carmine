# Carmine

Carmine is a red-team queue for startup founders. This repository contains the
platform skeleton plus the Step 2 LLM and embedding layer. It has no retrieval,
attack modules, scoring, or real objection prompts yet.

## Repository layout

- `frontend/` React + Vite static app
- `backend/` FastAPI service and portable SQL migrations
- `.github/workflows/` CI, keep-alive, and Turso smoke-test workflows
- `render.yaml` Render blueprint

## Local setup

1. Create a Supabase project. Enable Google and Email providers under
   Authentication, and add `http://localhost:5173` to the redirect URLs.
2. Create a Turso database for hosted use, or leave `TURSO_DATABASE_URL` empty
   for local SQLite.
3. Copy the examples:

   ```sh
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```

4. Fill in the variables described below. Never commit either `.env` file.
5. Run the backend:

   ```sh
   cd backend
   python -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```

6. In another terminal run the frontend:

   ```sh
   cd frontend
   npm install
   npm run dev
   ```

The first backend start applies all migrations to `backend/data/carmine.db`.

## Environment variables

Backend (`backend/.env`):

- `SUPABASE_URL`: Supabase Project URL from Project Settings > API.
- `SUPABASE_ANON_KEY`: Supabase publishable/anon key. It is used only for
  Supabase Auth verification and is not a database secret.
- `TURSO_DATABASE_URL`: Turso database URL from `turso db show --url`; leave
  blank locally to use SQLite.
- `TURSO_AUTH_TOKEN`: database token from `turso db tokens create`; required
  when `TURSO_DATABASE_URL` is set.
- `DATABASE_PATH`: optional local SQLite path, default `data/carmine.db`.
- `CORS_ORIGINS`: comma-separated browser origins, for example
  `http://localhost:5173`.
- `LLM_CONFIG_PATH`: optional path to the provider routing TOML. LLM code is
  used by pipeline scripts, not imported at web-service startup.
- `LLM_CACHE_TTL_SECONDS`: cache lifetime, default 86400 seconds.
- `LLM_MAX_ATTEMPTS` and `LLM_MAX_TOTAL_WAIT_SECONDS`: retry caps.
- `LLM_MAX_OVERLOAD_RETRIES`: maximum retries for 429/503/overload responses.
- `LLM_CIRCUIT_FAILURE_COUNT` and `LLM_CIRCUIT_COOLDOWN_SECONDS`: per-model
  overload circuit-breaker settings.
- `LLM_DEBUG_LOCAL`: must remain `false` in production; full prompt/response
  debug logging is intentionally not enabled by default.
- `CARMINE_ENV`: use `production` to refuse local debug mode.
- `GEMINI_API_KEY`, `GROQ_API_KEY`: local/pipeline-only model keys. Do not add
  these to Render.

Frontend (`frontend/.env`):

- `VITE_SUPABASE_URL`: same Supabase Project URL.
- `VITE_SUPABASE_ANON_KEY`: same public/anon key. Never put a service-role or
  Turso token here.
- `VITE_API_URL`: FastAPI URL, for example `http://localhost:8000`.

GitHub Actions secrets/variables are documented in `.github/workflows/README.md`.

## Step 2 LLM and embeddings

Provider routing and model IDs live in `backend/app/llm/config.toml`, not in
Python code. `LLMClient.complete()` is the single structured/text completion
entry point. It applies ordered fallback, bounded retries with jitter and
`Retry-After`, Pydantic validation plus one repair attempt, provider rate and
daily guards, database caching, and privacy-safe `llm_calls` logging. It also
applies per-purpose deadlines and per-model overload circuit breakers.
`llm_calls` stores one row per provider attempt with HTTP status and attempt
latency; completion metadata separately includes total call latency across
retries.

The `EmbeddingEngine` uses CPU-only `BAAI/bge-small-en-v1.5`, pinned to
revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, with 384 dimensions.
Embeddings and cache rows are startup-scoped when a startup ID is available;
startup deletion purges both. The model is loaded only by pipeline scripts and
tests, never by the Render web service.

Run the provider probe and usage report locally from `backend` after installing
the pipeline dependencies:

```sh
pip install -r requirements-pipeline.txt
python scripts/llm_check.py
python scripts/usage_report.py
python scripts/embedding_benchmark.py
```

The provider probe prints only provider/model names, status, latency, and token
counts. The GitHub Actions workflows `LLM provider check` and `Embedding
benchmark` are manual triggers.

## Tests

```sh
cd backend
pip install -r requirements.txt
pytest
```

Tests use an in-memory SQLite database and stub verified Supabase claims. The
isolation tests cover one user attempting to read another user's startup and
objections.

## Deploying

1. Create the Turso database and token.
2. Create the Supabase project, configure Google and magic-link redirect URLs,
   and copy the project URL and public key.
3. Connect this repository to Render and use `render.yaml`. Set the backend
   secrets and `CORS_ORIGINS` to the final Render static-site URL. Set the
   frontend variables to the final backend URL.
4. Add the GitHub Actions secrets in `.github/workflows/README.md` and run the
   manual Turso smoke workflow once.
5. After deployment, check `/health`, sign in, create a startup, and confirm
   its queue is empty.

The production service selects remote Turso when `TURSO_DATABASE_URL` is set;
it never writes a local database file in that mode. Render's filesystem is
ephemeral, so all production data belongs in Turso.

Supabase currently pauses Free projects with low database activity over a
seven-day period. The keep-alive workflow creates activity, but Supabase says
this is not a guarantee; check the dashboard before tester sessions or use a
paid plan for a no-pause guarantee.

## Current scope and known limitations

### Step 3 API changelog

The API now implements the frontend-facing assumptions, queued runs, objection
review, validation-task, and telemetry endpoints. All protected routes require
the Supabase bearer token and scope every lookup through the authenticated
user's startup or session.

- Assumptions: `POST /startups/{id}/assumptions/extract` accepts `{ "text" }`
  and returns `{ "assumptions": [{ "text", "category" }] }` without saving
  anything; `GET` lists rows; `POST` accepts `{ "text", "category" }`; and
  `PATCH /assumptions/{id}` accepts editable fields plus `status` of
  `proposed`, `confirmed`, or `retired`.
- Runs: `POST /startups/{id}/runs` returns a queued run; `GET` lists runs and
  `GET /runs/{id}` returns its status. A confirmed assumption is required and
  the per-startup daily limit is configurable.
- Objections: the list endpoint supports `status`, `module`, `assumption_id`
  (or `general`), `severity`, `limit`, and `offset`. Detail includes evidence,
  source fields, and verdict history. Verdict accepts `accept`, `rebut`,
  `investigate`, or `dismiss`, with optional `reason`, `response_plan`, and
  `time_spent_ms`. Investigate creates an open validation task. A counter is
  available only after `rebut`, once per verdict.
- Validation tasks: `GET /startups/{id}/validation-tasks` lists tasks and
  `PATCH /validation-tasks/{id}` accepts `{ "status" }`.
- Telemetry: `POST /sessions` starts a server-timestamped session,
  `PATCH /sessions/{id}` ends it with optional `{ "active_ms" }`, and
  `POST /events` accepts up to 100 `{ "session_id", "event", "objection_id" }`
  events. Supported events are `card shown`, `verdict start`, `verdict end`,
  `rebuttal start`, `rebuttal end`, `idle`, and `resumed`; event timestamps
  always come from the server.

Successful creates return `201`; invalid input returns `422`; missing or
cross-user resources return `404`; invalid checkpoint/state or a second
counter returns `409`; oversized requests return `413`; rate limits return
`429`; and exhausted interactive LLM providers return `503`. Errors use
`{ "error": { "code", "message", "details" } }`. High- or critical-severity
`rebut` and `dismiss` verdicts require a non-empty reason. Counter prompts use
only stored evidence and the founder's reason and explicitly forbid invented
sources; a failed model call does not consume the counter.

The endpoints do not run the retrieval pipeline yet. Briefs, admin,
stress-test, calibration, export, retrieval, pipeline work, and UI remain out
of scope for this step. Generate the frontend contract locally with:

```sh
cd backend
python -c 'from app.main import app; import json; print(json.dumps(app.openapi(), indent=2))' > ../openapi.json
```

