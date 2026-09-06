# ADR-017 — A result's lifecycle is its own row, not columns on the result

**Status:** Accepted · **Date:** 2026-09-06

## Context

SPEC-024 gives a result a lifecycle: received, reviewed, communicated, closed,
with the clinician's decision recorded against it. A result today is either a
`LabResult` (integer primary key, one row per measurement) or an
`ImagingStudy` (String(36) primary key, one row per study), and both are pure
records of what was measured.

Two shapes could hold the lifecycle.

**Columns on each result table.** Add `status`, `reviewed_by`, `reviewed_at`,
`disposition`, `note`, `closed_at` to `lab_results`, and the same six to
`imaging_studies`.

**A separate table** keyed on `(result_type, result_id)`, the way `tasks`
already references seven incompatible sources.

## Decision

A separate `result_reviews` table, unique on `(result_type, result_id)`.

## Rationale

**The two tables have incompatible keys, so "columns on the result" is two
implementations from the first day.** `LabResult.id` is an autoincrementing
integer and `ImagingStudy.id` is a UUID string. Every query that asks "what is
unreviewed" would have to be written twice and unioned, and every guard —
"closed requires a reviewer", "communicated requires a share" — would be two
constraints that agree until one is edited. `tasks` already made this choice for
exactly this reason (SPEC-018 §Modelo), and a second answer to the same question
in the same codebase is worse than either answer.

**A result is a measurement; a review is a human act.** They have different
authors, different timestamps, and different lifetimes: a lab value is true
forever and a review is one clinician's decision on one day. Putting
`reviewed_by` on `lab_results` makes the measurement look like it changed when
somebody read it. Keeping them apart also means the review carries PHI-encrypted
free text (`note`) without turning a numeric results table into one that needs
the encryption key to read at all.

**Adding six columns to `lab_results` costs every reader.** Four modules read
that table today for trends and deterioration, none of which cares about review
state. Widening a hot table for a concern none of its readers share is how
tables become unqueryable.

**A third result kind is coming.** Pathology, a document, a device upload —
each would be a third set of six columns under the column approach, and is a new
`result_type` value under this one.

## Consequences

- No referential integrity from the review to its result, the same cost `tasks`
  accepted. It is contained the same way: a check constraint on the closed list
  of `result_type` values, and a uniqueness constraint that makes a duplicate
  lifecycle impossible.
- "Show me this result and its review" is a join rather than a row. It is one
  join, on an indexed pair, in a query that already loads the patient.
- The intake path has to create both rows in one transaction, so a result can
  never exist without a lifecycle. That is a service-layer invariant rather than
  a schema one, and it is where the test goes.
- `ResultShare` gains a nullable `(result_type, result_id)` rather than being
  migrated. Existing shares point at timeline events and keep doing so — the
  link is additive, because rewriting historical shares to point somewhere else
  would rewrite what was actually shared.

## Alternatives considered

**Columns on each result table.** Rejected above: two implementations of one
concept, forced by the key types, on a table whose existing readers do not care.

**One `results` supertable that both kinds write into.** The clean answer, and a
much larger change: it means rewriting `LabResult`'s four readers, migrating
`imaging_studies`, and inventing timestamps for the `Patient.lab_results` panel
that has none. SPEC-024 §11 risk 2 records that the duplication is narrowed
rather than solved, which is honest about what this phase actually did.

**A `status` column on `LabResult` alone, imaging later.** Cheapest, and it
builds the thing that has to be undone: the moment imaging joins, the query
that lists unreviewed results is two queries, and the second one is written by
somebody who has forgotten the first one's guards.
