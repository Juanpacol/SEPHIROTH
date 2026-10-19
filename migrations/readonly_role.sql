-- Read-only role for looking at a database without being able to change it
-- (AB#18). Use it to inspect production: `scripts/inspect_db.py` refuses any
-- role that can write, so the owner role cannot be used by mistake.
--
-- Run this ONCE, connected as the owner role, against the target database
-- (Supabase's SQL editor, or psql against the local docker-compose Postgres).
-- Idempotent -- safe to re-run after a later migration adds tables, since the
-- explicit GRANT covers what exists and ALTER DEFAULT PRIVILEGES covers what
-- the owner creates afterwards.
--
-- Replace `change-me-generate-a-real-secret` with a generated password
-- (`openssl rand -hex 24`) BEFORE running it, and never commit the result.
-- On Supabase the owner role is `postgres` and the database is `postgres`:
-- replace the database name below and `clinical_ai` in the ALTER DEFAULT
-- PRIVILEGES statement, as in `roles.sql`.

DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'clinical_ai_readonly') THEN
      CREATE ROLE clinical_ai_readonly LOGIN PASSWORD 'change-me-generate-a-real-secret';
   END IF;
END
$$;

GRANT CONNECT ON DATABASE clinical_ai_db TO clinical_ai_readonly;
GRANT USAGE ON SCHEMA public TO clinical_ai_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO clinical_ai_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE clinical_ai IN SCHEMA public GRANT SELECT ON TABLES TO clinical_ai_readonly;

-- Belt and braces: even if some other grant ever reaches this role, every
-- session it opens is read-only.
ALTER ROLE clinical_ai_readonly SET default_transaction_read_only = on;

-- Explicitly not granted: INSERT/UPDATE/DELETE/TRUNCATE, CREATE/ALTER/DROP,
-- ownership of anything.
