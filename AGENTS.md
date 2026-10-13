## Development

You can assume that it all servers are already running in correct ports via .tmuxp.conf

## Project: SE-INT-04 Weekly Planning SaaS

### Tenancy & Security
- Every database query MUST be scoped by `org_id`. No query fetches by ID alone.
- Cross-org access attempts return 404, not 403 (don't leak existence).
- Platform staff means `is_admin` on the User model. The organization-level role is always called `org_role` (string on the membership). Keep the two distinct everywhere.
- Suspended orgs and deactivated users are rejected on every request — tokens issued before suspension/deactivation stop working.

### Testing
- Tests are REQUIRED. This overrides the template default of "optional in MVP".
- Every new endpoint needs a cross-org isolation test.
- AI tests use `TestModel`/`FunctionModel` — no test may call Gemini.
- Run `uv run pytest` with no network access to Google.

### AI Safety
- Never log prompt text or response text. Only log metadata to `ai_calls` table.
- AI output uses typed Pydantic `output_type` and goes to forms, never straight to the DB.
- Agents get no tools — plan text is untrusted input.

### Conventions (from Launchbase)
- Use `uv run` for all Python commands.
- `uv run alembic revision --autogenerate` for migrations. Only manual edit: adding `server_default` for nullable situations.
- Don't use enums in models due to Alembic migration issues.
- Services `flush()`, routers `commit()`.
- `npm run generate` for the typed frontend client after API changes.
- Use common REST API design guidelines.
- Update `requests.org` when changing APIs.
