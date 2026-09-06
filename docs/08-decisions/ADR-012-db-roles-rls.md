# ADR-012 — Least-privilege DB role; RLS not applicable

**Status:** Accepted · **Date:** 2026-09-04

## Context

A security audit (19-point checklist) flagged two related database controls:
a dedicated, least-privilege application role separate from the schema owner,
and Postgres Row Level Security (RLS).

## Decision

**DB role:** `migrations/roles.sql` creates `clinical_ai_app` — `SELECT`/
`INSERT`/`UPDATE`/`DELETE` on every table, no `CREATE`/`ALTER`/`DROP`, no
ownership. `DATABASE_URL` (the app's runtime connection) points at this role;
a new, optional `MIGRATION_DATABASE_URL` points at the schema-owning role and
is what `alembic upgrade head` uses when set (`migrations/env.py`), so
`init_db()`'s boot-time migration step keeps working without granting the
runtime role any DDL. Unset, behavior is unchanged from before this setting
existed (both run as `DATABASE_URL`'s role) — this is opt-in hardening, not a
breaking default. See `docs/04-development/setup.md`'s "Database roles".

**RLS: not applicable, by design, today.** `CLAUDE.md` decision #7/#20 is
explicit — patients are shared across every clinician (no per-clinician
scoping), and there is exactly one tenant in this system's data model. RLS
exists to enforce row-level isolation *between* tenants; with none, a native
Postgres RLS policy would either allow everything (a no-op) or need to encode
the same "every clinician sees every patient" rule the application layer
already enforces — duplicated logic with no additional guarantee. Enabling it
here would be security theater, not a real control.

## Revisit when

The patient-sharing model changes (per-clinician or per-organization scoping
is introduced) — at that point RLS becomes a genuine defense-in-depth layer
underneath the application-level checks, and this decision should be
revisited alongside whatever design doc introduces that scoping.
