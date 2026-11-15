# GitHub Actions setup

Add these repository secrets: `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`TURSO_DATABASE_URL`, and `TURSO_AUTH_TOKEN`. The workflows use the public
health URL in `API_HEALTH_URL` (a repository variable) and the Supabase URL for
the daily activity request. Set `API_HEALTH_URL` to the deployed `/health`
endpoint. The manual workflow inserts a row in `workflow_checks`.
