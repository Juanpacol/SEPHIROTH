-- Least-privilege application role, separate from the schema-owning role
-- migrations run as (`clinical_ai` locally / the Supabase project owner).
--
-- Run this ONCE, connected as the owner role, against the target database
-- (local docker-compose Postgres or Supabase's SQL editor / psql). It is
-- idempotent — safe to re-run after adding new tables via a later
-- migration, since `ALTER DEFAULT PRIVILEGES` covers tables created by the
-- owner role AFTER this statement runs, and the explicit GRANTs below cover
-- every table that already exists at the time you re-run it.
--
-- After running this, point the app's `DATABASE_URL` at `clinical_ai_app`
-- (never at the owner role) and, if you want migrations to keep running as
-- part of app boot, set `MIGRATION_DATABASE_URL` to the owner role's
-- connection string. See docs/04-development/setup.md's "Database roles".
--
-- On Supabase: the owner role is `postgres`, not `clinical_ai`, and the
-- database is `postgres`, not `clinical_ai_db` — replace both below
-- (search this file for `clinical_ai_db` and the two `clinical_ai` owner
-- references in the ALTER DEFAULT PRIVILEGES statements) before running it
-- in the Supabase SQL editor.

DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'clinical_ai_app') THEN
      CREATE ROLE clinical_ai_app LOGIN PASSWORD 'change-me-generate-a-real-secret';
   END IF;
END
$$;

GRANT CONNECT ON DATABASE clinical_ai_db TO clinical_ai_app;
GRANT USAGE ON SCHEMA public TO clinical_ai_app;

-- Every table/sequence that already exists.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO clinical_ai_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO clinical_ai_app;

-- Every table/sequence a future migration creates, as long as it runs as
-- the owner role below (never as clinical_ai_app itself — this role gets
-- no CREATE/ALTER/DROP anywhere).
ALTER DEFAULT PRIVILEGES FOR ROLE clinical_ai IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO clinical_ai_app;
ALTER DEFAULT PRIVILEGES FOR ROLE clinical_ai IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO clinical_ai_app;

-- Explicitly not granted: CREATE/ALTER/DROP on anything, ownership of any
-- table, CREATEDB/CREATEROLE/SUPERUSER. `clinical_ai_app` can read and
-- write rows; only the owner role can change the schema.
