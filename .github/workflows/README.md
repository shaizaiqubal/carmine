# GitHub Actions setup

Add these repository secrets: `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`TURSO_DATABASE_URL`, and `TURSO_AUTH_TOKEN`. The workflows use the public
health URL in `API_HEALTH_URL` (a repository variable) and the Supabase URL for
the daily activity request. Set `API_HEALTH_URL` to the deployed `/health`
endpoint. The manual workflow inserts a row in `workflow_checks`.

The manual LLM check also needs `GEMINI_API_KEY` and `GROQ_API_KEY`. It runs
only in GitHub Actions and does not add those keys to Render. The embedding
benchmark caches pip and the Hugging Face cache and installs the CPU PyTorch
wheel; it does not need API keys.
