# Carmine

Carmine is a red-team queue for startup founders. This repository currently
contains the platform skeleton only: authentication, startup profiles, an
empty objection queue, portable migrations, and deployment plumbing. It has
no LLM, retrieval, scoring, or other AI features yet.

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

Frontend (`frontend/.env`):

- `VITE_SUPABASE_URL`: same Supabase Project URL.
- `VITE_SUPABASE_ANON_KEY`: same public/anon key. Never put a service-role or
  Turso token here.
- `VITE_API_URL`: FastAPI URL, for example `http://localhost:8000`.

GitHub Actions secrets/variables are documented in `.github/workflows/README.md`.

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

Implemented endpoints are `GET /health`, `GET /me`, `POST/GET /startups`, and
`GET /startups/{id}/objections`. The objection endpoint intentionally returns
an empty list. The remaining API table, AI pipeline, verdicts, and weekly jobs
are not implemented in this step.

