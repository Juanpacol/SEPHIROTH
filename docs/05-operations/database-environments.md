# Database environments (AB#18)

Each environment has its own database, and nothing in development or test can reach production by accident.

| Environment | Database | Reached by |
|---|---|---|
| Production | Supabase (managed Postgres), database `postgres` | Render, `DATABASE_URL` set in the Render dashboard (never in the repo) |
| Local | docker-compose Postgres `sephiroth-postgres`, database `clinical_ai_db`, host port 5433 | `.env` `DATABASE_URL`; `docker compose` always uses its own `postgres` service |
| Tests | SQLite in memory; the local Postgres on 5433 for RAG tests | `tests/conftest.py` |
| CI | A throwaway Postgres container per run | `ci.yml` |

## The guards

- **The app refuses a remote database outside staging and production.** A `DATABASE_URL` or `MIGRATION_DATABASE_URL` on a remote host stops startup with an error naming the host (never the password). Local means loopback, private addresses, `host.docker.internal`, `.local`/`.internal` names and a bare name with no dot (a compose service). `ALLOW_REMOTE_DB=true` lifts it for someone who means it.
- **The test suite refuses a remote database whatever `ALLOW_REMOTE_DB` says**, before any test runs.
- **`docker compose` does not read `DATABASE_URL`.** The `api` container always uses the local `postgres` service. To point it elsewhere you must say so by name: `API_DATABASE_URL=... API_ALLOW_REMOTE_DB=true docker compose up`.
- **Production is untouched.** `ENVIRONMENT=production` (set in `render.yaml`) skips the check.

## Looking at production

Never with the owner role. Use a read-only role and `scripts/inspect_db.py`:

1. Once, in Supabase's SQL editor as the owner: run `migrations/readonly_role.sql` with a generated password (`openssl rand -hex 24`), replacing the database name and the owner role as its header explains.
2. Put its connection string in `.env.production.local` (git-ignored), under the name `INSPECT_DATABASE_URL` (not `DATABASE_URL`).
3. `python scripts/inspect_db.py` prints the migration version and row counts, never row contents. It refuses any role that can write or create, and opens a read-only transaction anyway.

## Moving the production connection out of `.env`

If your `.env` still holds the production `DATABASE_URL`, the app and the tests now refuse to start. Fix it once:

1. Replace `DATABASE_URL` in `.env` with the local one (`.env.example` has it).
2. Keep the production URL only where it is needed: Render's dashboard. For inspection, create the read-only role above instead of reusing the owner URL.
3. Remove `PHI_ENCRYPTION_KEY` for production from `.env`. The local database has its own data and needs its own key; mixing them makes the app fail closed when it reads a row the other key wrote.

## Least-privilege roles in production (a step you do in Supabase)

Today the app connects as the project owner, so it can run DDL. To narrow that:

1. Run `migrations/roles.sql` as the owner (replace the password and the Supabase names, as its header says). That creates `clinical_ai_app`: read and write rows, no DDL.
2. In Render set `DATABASE_URL` to `clinical_ai_app`'s connection string and `MIGRATION_DATABASE_URL` to the owner's. Migrations keep running on boot as the owner; requests run as the app role.
3. Deploy and check `/health/ready` and the smoke test. If it fails, put the previous `DATABASE_URL` back in Render and redeploy: nothing in the schema changed.

## Rotating the database password

Reset it in Supabase (Project Settings, Database), update `DATABASE_URL` in Render, redeploy. If the app cannot connect afterwards, the old value is the only thing to restore; the data is not touched by a password change. Rotate `INSPECT_DATABASE_URL` the same way for the read-only role (`ALTER ROLE clinical_ai_readonly PASSWORD '...'`).

## Not covered

A staging environment with its own Supabase project and encryption key is a separate story.
